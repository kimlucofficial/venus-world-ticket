# VENUS WORLD — TICKET BOT

## Bản đã cấu hình

- Kênh bảng ticket: 1531744343608787105
- Category chung: 1531744347437924473
- HELPER: 1535493904000876614
- VTEAM: 1531744066218229830
- Kênh backup: 1553619054147797062
- Token đã nằm trong .env. Không chia sẻ ZIP này.

## Chạy

1. Trong Discord Developer Portal, chọn bot → Bot → Privileged Gateway Intents
   → bật MESSAGE CONTENT INTENT và Save Changes. Bản backup cần quyền này để đọc nội dung.
2. Mời bot vào server với scopes bot và applications.commands.
3. Cấp bot View Channels, Send Messages, Read Message History, Attach Files,
   Embed Links, Manage Channels, Manage Roles. Quyền đọc/gửi phải có hiệu lực trong
   kênh bảng, category ticket và kênh backup. Giữ kênh backup riêng cho staff.
4. Windows có Python 3.12+: chạy start.bat, lần đầu tự cài thư viện.
5. Dùng /ticket_setup bằng tài khoản có Manage Server để đăng/cập nhật bảng.

Railway: deploy service riêng bằng Dockerfile có sẵn. Có thể override cấu hình
bằng Variables. Các Variables đã đặt trước đó sẽ ưu tiên hơn .env; cập nhật
SUPPORT_ROLE_IDS=1535493904000876614,1531744066218229830 và
BACKUP_CHANNEL_ID=1553619054147797062 nếu bạn đang dùng Variables.
Chạy đúng một replica/instance. Không cần database hay volume lưu dữ liệu.

## Giao diện và quyền

Ảnh chính assets/ticket.png; khung Components V2 màu hồng giống bot welcome.
Ba nút Hỗ trợ / Báo lỗi / Donate tạo kênh cùng category:
vns-ht-ID, vns-fix-ID, vns-dn-ID. ID = Discord user ID người mở.
Mỗi người chỉ có một ticket đang mở. Chống trùng còn hoạt động sau restart.
Chỉ chủ ticket, HELPER, VTEAM, bot và Administrator xem được ticket mới.
Không kế thừa quyền category để tránh vô tình công khai ticket.

HELPER / VTEAM hoặc Administrator được đóng mọi ticket, kể cả ticket chính mình mở.
Người dùng thường không được đóng. Kiểm tra quyền ở cả nút đóng lẫn nút xác nhận.
Quyền staff xác định bằng hai role ID đã cấu hình hoặc quyền Administrator;
không tự cấp quyền chỉ vì một role trang trí được xếp cao hơn HELPER. Administrator vẫn có quyền quản lý kênh trực tiếp
trong Discord, bot không thể chặn quyền Administrator của nền tảng.
Role cấu hình áp dụng khi tạo ticket mới. Ticket cũ có thể cần quản trị viên
thêm quyền xem/gửi cho HELPER/VTEAM trong quyền kênh.

## Backup khi staff đóng

1. Tạm khóa gửi tin trong ticket để xuất nội dung.
2. Đọc toàn bộ lịch sử còn tồn tại tới thời điểm snapshot, theo thứ tự thời gian.
3. Xuất ZIP gồm transcript.txt (nội dung, tên/ID tác giả, timestamp UTC,
   ID tin nhắn, reply, embed/component và sticker URL) cùng file đính kèm tải về.
4. Gửi ZIP vào kênh backup cùng chủ ticket, staff đóng, channel ID và số tin.
5. Chỉ sau khi gửi backup thành công, đổi trạng thái sang closed và đổi tên kênh.

Không xóa kênh tự động: kênh đóng giữ lại lịch sử và bị khóa gửi tin cho các
đối tượng trong permission overwrites, trừ bot. Administrator vẫn vượt được
quyền khóa của Discord. Staff có thể kiểm tra ZIP rồi xóa kênh đóng bằng Discord.
Category giới hạn 50 kênh; bot thông báo nếu đầy để staff dọn ticket đã đóng.

Nếu đọc/tải file/gửi backup lỗi, bot không đóng ticket và thử khôi phục quyền cũ.
Nếu Discord không cho khôi phục quyền, bot báo rõ để quản trị viên sửa.
ZIP vượt giới hạn upload của server cũng giữ ticket mở và thông báo để staff
lưu riêng file lớn trước khi thử lại. Không âm thầm bỏ file đính kèm bị lỗi.
Nếu backup đã gửi nhưng đổi trạng thái lỗi, lần thử lại có thể tạo thêm bản backup.

Backup là snapshot nội dung hiện có: không khôi phục tin đã xóa, các phiên bản
trước khi sửa, nội dung thread riêng, hay file từ website ngoài; embed/sticker
lưu dữ liệu/URL, không tải tài nguyên bên ngoài. Không dựa vào URL đính kèm cũ:
file đính kèm của tin nhắn được tải và đóng gói trực tiếp trong ZIP.
Không thay đổi topic ticket vì đó là metadata để bot nhận diện sau restart.

/ticket_controls: Manage Server có thể khôi phục bảng điều khiển trong ticket mở.
Nút persistent hoạt động sau restart. Xác nhận đóng tạm thời hết hạn sau 60 giây;
nhấn Đóng ticket lại để mở xác nhận mới.

## Kiểm tra

python3 -m unittest -v

Đã qua 10 bài kiểm tra offline: Components V2/persistent buttons, tạo ba loại,
quyền riêng tư và chống trùng đồng thời, rollback khi tạo thiếu bảng, từ chối
người dùng thường đóng, cho phép staff/admin đóng ticket tự mở, xuất ZIP có text và bytes đính kèm,
backup thành công mới đóng và khôi phục quyền khi backup thất bại;
4 emoji mới, bảng staff ephemeral và nút báo bận có kiểm tra quyền.
Chưa đăng nhập chạy thử trên server thật. Bot yêu cầu Message Content Intent;
nếu chưa bật trong Developer Portal, kết nối có thể báo lỗi privileged intents.
API: https://discordpy.readthedocs.io/en/latest/api.html

## Bản cập nhật icon và bảng staff

Đã dùng ba emoji động bạn cung cấp cho Hỗ trợ/Báo lỗi/Donate trong nội dung và nút,
icon động trước dòng Chọn mục và footer: Vui lòng không spam ticket dưới mọi hình thức.
Sau khi thay source và Redeploy Railway, dùng /ticket_setup để cập nhật bảng cũ.
Nếu emoji ở server khác, cấp quyền Use External Emojis cho bot khi cần.

Trong ticket mở, HELPER/VTEAM/Administrator dùng /ticket_staff để hiện bảng nút
riêng (ephemeral, chỉ người gọi thấy): BQT đang bận và Đóng ticket. Bảng hết hạn
sau 5 phút hoặc khi bot restart; dùng lại lệnh để mở bảng mới.
Nút báo bận gửi: Hiện tại BQT đang bận, cư dân vui lòng chờ sau ít phút.
Người mở ticket thường không nhìn thấy bảng nút riêng; họ nhìn thấy thông báo
được gửi sau khi staff bấm. Người thường thử lệnh cũng bị từ chối, không nhận bảng.
Discord không hỗ trợ ẩn từng nút theo role trong cùng một tin nhắn công khai.
Tên slash command có thể xuất hiện trong danh sách lệnh của người thường;
quyền sử dụng vẫn được kiểm tra ở server mỗi lần gọi/bấm.
