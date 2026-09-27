from __future__ import annotations
import asyncio
import logging
import os
import json
import tempfile
import zipfile
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / '.env')
TOKEN = os.getenv('DISCORD_TOKEN', '').strip()
PANEL_ID = int(os.getenv('TICKET_CHANNEL_ID', '1531744343608787105'))
CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', '1531744347437924473'))
STAFF_IDS = {int(x.strip()) for x in os.getenv('SUPPORT_ROLE_IDS', '1535493904000876614,1531744066218229830').split(',') if x.strip()}
BACKUP_ID = int(os.getenv('BACKUP_CHANNEL_ID', '1553619054147797062'))
COLOR = discord.Colour.from_rgb(225, 126, 214)
KINDS = {'ht': ('Hỗ trợ', '<a:Manao18:1553623507810918410>'), 'fix': ('Báo lỗi', '<a:18212kittypaw22:1553624799266472006>'), 'dn': ('Donate', '<a:625725purplepresent:1553623981909614723>')}
log = logging.getLogger('venus-ticket')
locks: dict[int, asyncio.Lock] = {}


def lock_for(guild_id):
    return locks.setdefault(guild_id, asyncio.Lock())


def metadata(channel):
    parts = (getattr(channel, 'topic', None) or '').split('|')
    if len(parts) == 5 and parts[0] == 'venus-ticket-v1' and parts[1].isdigit() and parts[2] in KINDS and parts[3] in ('open', 'closed') and parts[4].isdigit():
        return int(parts[1]), parts[2], parts[3], int(parts[4])
    return None


def is_staff(member):
    return isinstance(member, discord.Member) and (member.guild_permissions.administrator or any(r.id in STAFF_IDS for r in member.roles))


def can_close(member, owner_id):
    # Authorization depends on staff permissions, not ticket ownership.
    return is_staff(member)


async def export_backup(client, channel, data, closer):
    backup = await client.fetch_channel(BACKUP_ID)
    if not isinstance(backup, discord.TextChannel) or backup.guild.id != channel.guild.id or backup.id == channel.id:
        raise RuntimeError('Kênh backup không hợp lệ hoặc khác server.')
    cutoff = discord.utils.utcnow()
    with tempfile.TemporaryDirectory(prefix='venus-ticket-') as folder:
        root = Path(folder)
        archive = root / f'ticket-{channel.id}.zip'
        transcript = root / 'transcript.txt'
        count = 0
        with transcript.open('w', encoding='utf-8') as out, zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            out.write(f'VENUS WORLD — BACKUP TICKET\nKênh: {channel.name} ({channel.id})\n'
                      f'Người mở: {data[0]}\nLoại: {KINDS[data[1]][0]}\n'
                      f'Staff đóng: {closer} ({closer.id})\nThời điểm snapshot UTC: {cutoff.isoformat()}\n'
                      'Nội dung hiện có tại thời điểm xuất; tin đã xóa và phiên bản trước khi sửa không khôi phục được.\n\n')
            async for msg in channel.history(limit=None, oldest_first=True, before=cutoff):
                count += 1
                out.write(f'[{msg.created_at.isoformat()}] {msg.author} ({msg.author.id}) | Message ID: {msg.id}\n')
                if msg.edited_at:
                    out.write(f'Đã sửa: {msg.edited_at.isoformat()}\n')
                if msg.reference:
                    out.write(f'Trả lời message: {msg.reference.message_id}\n')
                out.write((msg.content or msg.system_content or '') + '\n')
                for embed in msg.embeds:
                    out.write('Embed: ' + json.dumps(embed.to_dict(), ensure_ascii=False) + '\n')
                for component in msg.components:
                    out.write('Component: ' + json.dumps(component.to_dict(), ensure_ascii=False) + '\n')
                for sticker in msg.stickers:
                    out.write(f'Sticker: {sticker.name} — {sticker.url}\n')
                for attachment in msg.attachments:
                    # Safe archive paths; original filename stays in the transcript.
                    suffix = Path(attachment.filename).suffix[:16]
                    local = root / f'{msg.id}-{attachment.id}{suffix}'
                    await attachment.save(local)
                    name = 'attachments/' + local.name
                    z.write(local, name)
                    local.unlink()
                    out.write(f'Đính kèm: {attachment.filename} -> {name}\n')
                out.write('\n')
            out.flush()
            z.write(transcript, 'transcript.txt')
        if archive.stat().st_size > backup.guild.filesize_limit:
            raise RuntimeError('File backup vượt giới hạn upload của server. Ticket chưa đóng; hãy lưu riêng file lớn trước khi thử lại.')
        file = discord.File(archive)
        try:
            message = await backup.send(
                content=f'📁 **BACKUP TICKET** • `{channel.name}`\n'
                        f'Chủ ticket: <@{data[0]}> • Staff: <@{closer.id}>\n'
                        f'Kênh ID: `{channel.id}` • {count} tin nhắn • Snapshot UTC: `{cutoff.isoformat()}`',
                file=file, allowed_mentions=discord.AllowedMentions.none())
        finally:
            file.close()
        return message.jump_url


async def tell(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


class SafeView(discord.ui.LayoutView):
    async def on_error(self, interaction, error, item):
        log.error('Lỗi xử lý ticket', exc_info=(type(error), error, error.__traceback__))
        await tell(interaction, '❌ Không thực hiện được. Hãy kiểm tra quyền bot hoặc liên hệ quản trị viên.')


class OpenButton(discord.ui.Button):
    def __init__(self, kind):
        label, emoji = KINDS[kind]
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, custom_id=f'venus:open:{kind}')
        self.kind = kind

    async def callback(self, interaction):
        await create_ticket(interaction, self.kind)


class Panel(SafeView):
    def __init__(self):
        super().__init__(timeout=None)
        box = discord.ui.Container(accent_colour=COLOR)
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media='attachment://ticket.png', description='Venus World — Ticket hỗ trợ')
        box.add_item(gallery)
        box.add_item(discord.ui.Separator())
        box.add_item(discord.ui.TextDisplay(
            '## <:96359bubbleheart:1532387513031721101> TRUNG TÂM HỖ TRỢ\n'
            '<a:SaF_Bluerollingstar:1532586674952081519> **Venus World luôn sẵn sàng hỗ trợ bạn!**\n\n'
            '<a:Manao18:1553623507810918410> **Hỗ trợ** — Giải đáp thắc mắc, hỗ trợ trong thành phố.\n'
            '<a:18212kittypaw22:1553624799266472006> **Báo lỗi** — Gửi lỗi gặp phải kèm hình ảnh hoặc video.\n'
            '<a:625725purplepresent:1553623981909614723> **Donate** — Tư vấn và hỗ trợ đóng góp cho Venus World.\n\n'
            '<a:1357882491800911983:1553623193082794058> **Chọn mục bên dưới để mở phòng trao đổi riêng.**\n'
            '-# Vui lòng không spam ticket dưới mọi hình thức.'
        ))
        box.add_item(discord.ui.ActionRow(*(OpenButton(kind) for kind in KINDS)))
        self.add_item(box)


class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Đóng ticket', emoji='🔒', style=discord.ButtonStyle.danger, custom_id='venus:close')

    async def callback(self, interaction):
        channel = interaction.channel
        data = metadata(channel)
        if not data or data[3] != interaction.client.user.id or channel.category_id != CATEGORY_ID:
            return await tell(interaction, 'Đây không phải ticket của bot này.')
        if not can_close(interaction.user, data[0]):
            return await tell(interaction, 'Chỉ HELPER / VTEAM hoặc Administrator được đóng ticket.')
        if data[2] == 'closed':
            return await tell(interaction, 'Ticket đã đóng rồi.')
        await interaction.response.send_message('Xuất nội dung và file đính kèm sang kênh backup rồi đóng ticket?', view=ConfirmClose(channel.id), ephemeral=True)


class BusyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='BQT đang bận', emoji='⏳', style=discord.ButtonStyle.secondary,
                         custom_id='venus:staff:busy')

    async def callback(self, interaction):
        if not is_staff(interaction.user):
            return await tell(interaction, 'Chỉ HELPER / VTEAM hoặc Administrator được dùng nút này.')
        await interaction.response.defer(ephemeral=True)
        async with lock_for(interaction.guild_id):
            channel = await interaction.guild.fetch_channel(interaction.channel_id)
            data = metadata(channel)
            if not data or data[3] != interaction.client.user.id or channel.category_id != CATEGORY_ID or data[2] != 'open':
                return await tell(interaction, 'Nút này chỉ dùng trong ticket đang mở của bot.')
            await channel.send('⏳ **Hiện tại BQT đang bận, cư dân vui lòng chờ sau ít phút.**',
                               allowed_mentions=discord.AllowedMentions.none())
            await tell(interaction, '✅ Đã gửi thông báo BQT đang bận vào ticket.')


class StaffView(SafeView):
    def __init__(self):
        super().__init__(timeout=300)
        box = discord.ui.Container(accent_colour=COLOR)
        box.add_item(discord.ui.TextDisplay('## ĐIỀU KHIỂN TICKET\nBảng riêng dành cho HELPER / VTEAM / Administrator.'))
        box.add_item(discord.ui.ActionRow(BusyButton(), CloseButton()))
        self.add_item(box)


class TicketView(SafeView):
    def __init__(self, owner_id=0, kind='ht'):
        super().__init__(timeout=None)
        label, emoji = KINDS[kind]
        box = discord.ui.Container(accent_colour=COLOR)
        box.add_item(discord.ui.TextDisplay(
            f'## {emoji} KÊNH {label.upper()}\n'
            f'Chào <@{owner_id}>! Hãy mô tả yêu cầu của bạn và đính kèm hình ảnh/video nếu có.\n\n'
            'Đội hỗ trợ sẽ phản hồi tại đây. Cảm ơn bạn đã chờ!\n'
            '-# Chỉ đội hỗ trợ được đóng ticket. Nội dung sẽ được lưu vào kênh backup.'
        ))
        box.add_item(discord.ui.Separator())
        box.add_item(discord.ui.ActionRow(CloseButton()))
        self.add_item(box)


class ConfirmClose(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=60)
        self.channel_id = channel_id

    @discord.ui.button(label='Xác nhận đóng', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        async with lock_for(interaction.guild_id):
            channel = await interaction.guild.fetch_channel(self.channel_id)
            data = metadata(channel)
            if not data or data[3] != interaction.client.user.id or channel.category_id != CATEGORY_ID or not can_close(interaction.user, data[0]):
                return await tell(interaction, 'Bạn không có quyền đóng ticket này.')
            if data[2] == 'closed':
                return await tell(interaction, 'Ticket đã đóng rồi.')
            original = channel.overwrites
            frozen = {target: discord.PermissionOverwrite.from_pair(*overwrite.pair()) for target, overwrite in original.items()}
            for target, overwrite in frozen.items():
                if target.id != interaction.client.user.id:
                    overwrite.update(send_messages=False, add_reactions=False, create_public_threads=False,
                                     create_private_threads=False, send_messages_in_threads=False)
            frozen.setdefault(channel.guild.default_role, discord.PermissionOverwrite()).update(
                send_messages=False, send_messages_in_threads=False)
            changed = False
            try:
                await channel.edit(overwrites=frozen, reason='Freeze ticket for backup')
                changed = True
                backup_url = await export_backup(interaction.client, channel, data, interaction.user)
                await channel.edit(name=f'closed-vns-{data[1]}-{data[0]}',
                    topic=f'venus-ticket-v1|{data[0]}|{data[1]}|closed|{data[3]}',
                    reason=f'Ticket closed by {interaction.user.id}; backup {backup_url}')
            except Exception as error:
                log.exception('Backup/close failed')
                restored = not changed
                if changed:
                    try:
                        await channel.edit(overwrites=original, reason='Restore ticket after backup/close failure')
                        restored = True
                    except discord.HTTPException:
                        log.exception('Could not restore permissions')
                detail = str(error) if isinstance(error, RuntimeError) else 'Kiểm tra quyền đọc lịch sử, gửi file và quyền quản lý kênh của bot.'
                await tell(interaction, f'❌ Chưa đóng ticket. {detail} ' +
                    ('Quyền gửi tin đã được giữ/khôi phục.' if restored else 'Không khôi phục được quyền gửi tin; quản trị viên cần mở lại quyền trong kênh.'))
                return
            await tell(interaction, f'✅ Đã backup và đóng ticket. Bản lưu: {backup_url}')
            try:
                await channel.send('🔒 **Ticket đã đóng.** Nội dung và file đính kèm đã được lưu vào kênh backup.')
            except discord.HTTPException:
                log.warning('Ticket closed but final notice could not be sent')
        self.stop()

    @discord.ui.button(label='Hủy', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content='Đã hủy thao tác đóng ticket.', view=None)
        self.stop()


async def get_locations(client):
    panel = await client.fetch_channel(PANEL_ID)
    category = await client.fetch_channel(CATEGORY_ID)
    if not isinstance(panel, discord.TextChannel) or not isinstance(category, discord.CategoryChannel) or panel.guild.id != category.guild.id:
        raise RuntimeError('Channel ticket và category phải đúng loại và cùng server.')
    return panel, category


async def create_ticket(interaction, kind):
    if not interaction.guild or interaction.channel_id != PANEL_ID or not isinstance(interaction.user, discord.Member):
        return await tell(interaction, 'Vui lòng dùng bảng ticket trong kênh hỗ trợ.')
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with lock_for(interaction.guild_id):
        panel, category = await get_locations(interaction.client)
        if category.guild.id != interaction.guild_id:
            return await tell(interaction, 'Cấu hình server không hợp lệ.')
        channels = await interaction.guild.fetch_channels()
        for channel in channels:
            data = metadata(channel)
            if data and data[0] == interaction.user.id and data[2] == 'open' and data[3] == interaction.client.user.id:
                return await tell(interaction, f'Bạn đã có ticket đang mở: {channel.mention}')
        if sum(c.category_id == CATEGORY_ID for c in channels) >= 50:
            return await tell(interaction, 'Category ticket đã đầy. Vui lòng báo quản trị viên dọn các ticket đã đóng.')
        roles = [interaction.guild.get_role(role_id) for role_id in STAFF_IDS]
        if any(role is None or role.is_default() for role in roles):
            return await tell(interaction, 'Cấu hình role hỗ trợ chưa đúng. Vui lòng liên hệ quản trị viên.')
        access = dict(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(**access, create_public_threads=False, create_private_threads=False),
            interaction.guild.me: discord.PermissionOverwrite(**access, manage_channels=True),
        }
        for role in roles:
            overwrites[role] = discord.PermissionOverwrite(**access)
        channel = await interaction.guild.create_text_channel(
            name=f'vns-{kind}-{interaction.user.id}', category=category,
            topic=f'venus-ticket-v1|{interaction.user.id}|{kind}|open|{interaction.client.user.id}',
            overwrites=overwrites, reason=f'Venus ticket: {interaction.user.id}',
        )
        try:
            await channel.send(view=TicketView(interaction.user.id, kind))
        except discord.HTTPException:
            # Remove an incomplete channel; if deletion fails, keep a useful link.
            try:
                await channel.delete(reason='Rollback incomplete ticket')
            except discord.HTTPException:
                log.exception('Ticket created but intro/rollback failed')
                return await tell(interaction, f'Đã tạo {channel.mention} nhưng thiếu bảng điều khiển. Hãy báo quản trị viên dùng /ticket_controls trong kênh đó.')
            raise
        await tell(interaction, f'✅ Đã mở ticket **{KINDS[kind][0]}**: {channel.mention}')


class TicketBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(Panel())
        self.add_view(TicketView())
        panel, _ = await get_locations(self)
        guild = discord.Object(id=panel.guild.id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


intents = discord.Intents.default()
intents.message_content = True
bot = TicketBot(command_prefix=commands.when_mentioned, intents=intents, allowed_mentions=discord.AllowedMentions.none())


@bot.event
async def on_ready():
    log.info('Venus Ticket online: %s', bot.user)


@bot.tree.command(name='ticket_setup', description='Đăng hoặc cập nhật bảng ticket Venus World')
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def ticket_setup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        return await tell(interaction, 'Bạn cần quyền Manage Server.')
    await interaction.response.defer(ephemeral=True)
    async with lock_for(interaction.guild_id):
        panel, _ = await get_locations(bot)
        if panel.guild.id != interaction.guild_id:
            return await tell(interaction, 'Lệnh này chỉ dùng trong server đã cấu hình.')
        # The panel survives restarts without relying on a local database.
        existing = None
        async for message in panel.history(limit=None):
            if message.author.id == bot.user.id and message.flags.components_v2:
                if any('venus:open:ht' in str(component.to_dict()) for component in message.components):
                    existing = message
                    break
        file = discord.File(BASE / 'assets/ticket.png', filename='ticket.png')
        if existing:
            await existing.edit(view=Panel(), attachments=[file])
        else:
            await panel.send(view=Panel(), file=file)
        await tell(interaction, f'✅ Bảng ticket đã sẵn sàng tại {panel.mention}.')


@bot.tree.command(name='ticket_staff', description='Mở bảng nút riêng dành cho đội hỗ trợ')
@app_commands.guild_only()
async def ticket_staff(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await tell(interaction, 'Chỉ HELPER / VTEAM hoặc Administrator được mở bảng này.')
    data = metadata(interaction.channel)
    if not data or data[3] != interaction.client.user.id or data[2] != 'open' or interaction.channel.category_id != CATEGORY_ID:
        return await tell(interaction, 'Hãy dùng /ticket_staff trong ticket đang mở của bot.')
    await interaction.response.send_message(view=StaffView(), ephemeral=True)


@bot.tree.command(name='ticket_controls', description='Khôi phục nút đóng trong ticket hiện tại')
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def ticket_controls(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        return await tell(interaction, 'Bạn cần quyền Manage Server.')
    data = metadata(interaction.channel)
    if not data or data[3] != bot.user.id or data[2] != 'open' or interaction.channel.category_id != CATEGORY_ID:
        return await tell(interaction, 'Hãy dùng trong một ticket đang mở của bot này.')
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(view=TicketView(data[0], data[1]))
    await tell(interaction, 'Đã khôi phục bảng điều khiển.')


@bot.tree.error
async def command_error(interaction, error):
    log.error('Slash command error', exc_info=(type(error), error, error.__traceback__))
    await tell(interaction, '❌ Không thực hiện được. Hãy kiểm tra quyền bot và log.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    if not TOKEN:
        raise SystemExit('Thiếu DISCORD_TOKEN. Điền token BOT TICKET RIÊNG vào .env hoặc Variables.')
    if not STAFF_IDS:
        log.warning('SUPPORT_ROLE_IDS trống: chỉ người tạo ticket và Administrator xem được ticket.')
    bot.run(TOKEN, log_handler=None)
