"""Offline checks; no token or Discord connection required."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import bot as app

class TicketTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_layout(self):
        panel = app.Panel()
        self.assertTrue(panel.is_persistent())
        data = str(panel.to_components())
        self.assertIn('attachment://ticket.png', data)
        for kind in app.KINDS:
            self.assertIn(f'venus:open:{kind}', data)
        self.assertTrue(app.TicketView().is_persistent())
        await app.bot.close()

    async def test_private_creation_and_concurrent_duplicates(self):
        for kind in app.KINDS:
            app.locks.clear()
            user = MagicMock(spec=discord.Member)
            user.id = 123456789
            everyone = MagicMock(spec=discord.Role)
            me = MagicMock(spec=discord.Member)
            guild = SimpleNamespace(id=123, default_role=everyone, me=me)
            channel = SimpleNamespace(id=88, mention='<#88>', category_id=app.CATEGORY_ID,
                topic=f'venus-ticket-v1|{user.id}|{kind}|open|99', send=AsyncMock(), delete=AsyncMock())
            channels = []
            guild.fetch_channels = AsyncMock(side_effect=lambda: list(channels))
            async def create(**kwargs):
                await asyncio.sleep(0)
                channels.append(channel)
                return channel
            guild.create_text_channel = AsyncMock(side_effect=create)
            def interaction():
                return SimpleNamespace(guild=guild, guild_id=123, channel_id=app.PANEL_ID, user=user,
                    client=SimpleNamespace(user=SimpleNamespace(id=99)),
                    response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True), followup=SimpleNamespace(send=AsyncMock()))
            a, b = interaction(), interaction()
            with patch.object(app, 'STAFF_IDS', set()), patch.object(app, 'get_locations', AsyncMock(return_value=(None, SimpleNamespace(guild=guild)))):
                await asyncio.gather(app.create_ticket(a, kind), app.create_ticket(b, kind))
            guild.create_text_channel.assert_awaited_once()
            args = guild.create_text_channel.call_args.kwargs
            self.assertEqual(args['name'], f'vns-{kind}-{user.id}')
            self.assertFalse(args['overwrites'][everyone].view_channel)
            self.assertTrue(args['overwrites'][user].view_channel)
            self.assertIn('đã có ticket', b.followup.send.call_args.args[0])

    async def test_failed_intro_rolls_back(self):
        app.locks.clear()
        user = MagicMock(spec=discord.Member); user.id = 123
        guild = MagicMock(); guild.id = 1
        guild.fetch_channels = AsyncMock(return_value=[])
        channel = MagicMock()
        response = SimpleNamespace(status=403, reason='Forbidden')
        channel.send = AsyncMock(side_effect=discord.Forbidden(response, 'Missing access'))
        channel.delete = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=channel)
        i = SimpleNamespace(guild=guild, guild_id=1, channel_id=app.PANEL_ID, user=user,
            client=SimpleNamespace(user=SimpleNamespace(id=99)), response=SimpleNamespace(defer=AsyncMock()))
        with patch.object(app, 'STAFF_IDS', set()), patch.object(app, 'get_locations', AsyncMock(return_value=(None, SimpleNamespace(guild=guild)))):
            with self.assertRaises(discord.Forbidden):
                await app.create_ticket(i, 'ht')
        channel.delete.assert_awaited_once()

    async def test_close_denies_outsider(self):
        i = SimpleNamespace(channel=SimpleNamespace(category_id=app.CATEGORY_ID, topic='venus-ticket-v1|123|ht|open|99'),
            client=SimpleNamespace(user=SimpleNamespace(id=99)), user=SimpleNamespace(id=456),
            response=SimpleNamespace(is_done=lambda: False, send_message=AsyncMock()))
        await app.CloseButton().callback(i)
        self.assertIn('Chỉ HELPER', i.response.send_message.call_args.args[0])

class BackupTests(unittest.IsolatedAsyncioTestCase):
    def staff(self, owner=False):
        member = MagicMock(spec=discord.Member)
        member.id = 123 if owner else 456
        member.guild_permissions.administrator = False
        member.roles = [SimpleNamespace(id=1535493904000876614)]
        return member

    async def test_owner_even_staff_cannot_close(self):
        self.assertFalse(app.can_close(self.staff(True), 123))
        self.assertTrue(app.can_close(self.staff(), 123))

    async def test_backup_includes_content_and_attachment(self):
        import zipfile
        from datetime import datetime, timezone
        backup = MagicMock(spec=discord.TextChannel)
        backup.guild = SimpleNamespace(id=1, filesize_limit=10_000_000)
        backup.id = app.BACKUP_ID
        async def receive(**kwargs):
            with zipfile.ZipFile(kwargs['file'].fp) as z:
                self.assertIn('Xin hỗ trợ', z.read('transcript.txt').decode())
                self.assertEqual(z.read('attachments/7-8.png'), b'image-bytes')
            return SimpleNamespace(jump_url='https://discord.com/channels/1/2/3')
        backup.send = AsyncMock(side_effect=receive)
        attachment = SimpleNamespace(id=8, filename='../proof.png')
        async def save(path):
            path.write_bytes(b'image-bytes')
        attachment.save = save
        msg = SimpleNamespace(id=7, created_at=datetime.now(timezone.utc), edited_at=None,
            author=SimpleNamespace(id=123), reference=None, content='Xin hỗ trợ',
            embeds=[], components=[], stickers=[], attachments=[attachment])
        async def history(**kwargs):
            yield msg
        channel = SimpleNamespace(id=9, name='vns-ht-123', guild=SimpleNamespace(id=1), history=history)
        client = SimpleNamespace(fetch_channel=AsyncMock(return_value=backup))
        await app.export_backup(client, channel, (123,'ht','open',99), self.staff())
        backup.send.assert_awaited_once()

    async def test_close_backup_failure_and_success(self):
        for fails in (True, False):
            app.locks.clear()
            everyone = MagicMock(spec=discord.Role); everyone.id=1
            owner = MagicMock(spec=discord.Member); owner.id=123
            channel = SimpleNamespace(id=9, category_id=app.CATEGORY_ID,
                topic='venus-ticket-v1|123|ht|open|99',
                guild=SimpleNamespace(default_role=everyone),
                overwrites={everyone:discord.PermissionOverwrite(view_channel=False),
                    owner:discord.PermissionOverwrite(view_channel=True,send_messages=True)},
                edit=AsyncMock(), send=AsyncMock())
            i=SimpleNamespace(guild_id=1, guild=SimpleNamespace(fetch_channel=AsyncMock(return_value=channel)),
                client=SimpleNamespace(user=SimpleNamespace(id=99)),user=self.staff(),
                response=SimpleNamespace(defer=AsyncMock(),is_done=lambda:True),
                followup=SimpleNamespace(send=AsyncMock()))
            async def export(*args):
                self.assertEqual(channel.edit.await_count,1)
                if fails: raise RuntimeError('backup unavailable')
                return 'https://discord.com/channels/1/2/3'
            with patch.object(app,'export_backup',side_effect=export):
                view=app.ConfirmClose(9)
                await view.confirm.callback(i)
            edits=channel.edit.call_args_list
            if fails:
                self.assertFalse(any('topic' in e.kwargs for e in edits))
                self.assertTrue(edits[-1].kwargs['overwrites'][owner].send_messages)
                channel.send.assert_not_awaited()
            else:
                self.assertIn('|closed|', edits[-1].kwargs['topic'])
                channel.send.assert_awaited_once()

if __name__ == '__main__':
    unittest.main()
