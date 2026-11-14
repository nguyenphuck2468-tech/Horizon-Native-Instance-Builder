# Hướng dẫn Horizon Native Instance Builder

Builder tạo native client Horizon cho Windows và Linux cùng bộ native mod đã được kiểm tra tương thích với đúng Nightly. Máy của bạn không phải tự biên dịch.

**Đầu ra đã được sửa:** artifact chứa thư mục instance thật theo cấu trúc `instances/<id>/`, không còn bắt bạn khôi phục một file `instance.zip` bằng chức năng Import/Restore.

## 1. Dữ liệu instance

Backup Horizon đặt tại:

- `input/instance/instance.zip` (khuyến nghị), hoặc
- `input/instance/horizon.zip` (tên cũ vẫn hỗ trợ).

Đây là dữ liệu instance như thế giới, cấu hình và dữ liệu người chơi. Builder kiểm tra ZIP, sau đó giải nén nội dung vào thư mục instance mới. File ZIP nguồn vẫn được giữ nguyên trong repo; checksum của nó được ghi vào manifest.

## 2. Bộ mod

Workflow tải phiên bản registry mới nhất và kiểm tra SHA-256, manifest cũng như báo cáo tương thích của đúng Horizon Nightly.

Danh sách mod đang yêu cầu:

- AppleSkin
- HUD+
- Fast Items
- Fullbright Horizon
- Jade
- JEI
- Zoom
- Enchantment Hints
- Inventory Profiles (chỉ được đưa vào nếu bản registry tương thích)

Freecam và Inventory Profiles không được ép cài nếu registry báo lỗi target trên Nightly hiện tại. Danh sách thực tế đã build được ghi trong artifact `registry-mod-selection`.

## 3. Chạy build

1. Mở repo Horizon Native Instance Builder.
2. Chọn **Actions → Build Horizon Native Instance → Run workflow**.
3. Để `minecraft_version` là `26.3` nếu vẫn khớp lock của Nightly.
4. Để trống `minecraft_release_tag` để runner tự tải runtime từ Mojang.
5. Chạy workflow và chờ Windows, Linux cùng bước xác minh hoàn tất.

## 4. Cài instance vào Horizon

Tải artifact `horizon-instance-windows-x86_64` và giải nén **một lần**. Bên trong sẽ có:

- `instances/horizon-native-<commit7>/`: thư mục instance thật, chứa dữ liệu đã giải nén.
- `native-build/windows-x86_64/horizon-client.exe`: native client.
- `build-inputs/mods/`: các gói .hnmod dùng để build.
- `build-manifest.json`: checksum và thông tin nguồn build.
- `README-INSTALL.txt`: hướng dẫn cài.

Thực hiện:

1. Chép nguyên thư mục `horizon-native-<commit7>` vào `GAME_HOME/instances/` của Horizon. Không chép vào thư mục cài chương trình launcher.
2. Mở PowerShell tại thư mục artifact và chạy:

       $build = horizon-launcher --json import-build "native-build/windows-x86_64/horizon-client.exe" --trust-unsigned | ConvertFrom-Json
       horizon-launcher instance version "horizon-native-<commit7>" $build.imported
       horizon-launcher instance select "horizon-native-<commit7>"

   Thay `<commit7>` bằng đúng tên thư mục trong artifact. Lệnh đầu trả về tag imported thật theo ngày và hash binary; không được tự đoán tag từ commit Horizon.
3. Mở Horizon Launcher. Instance mới sẽ xuất hiện trong danh sách và dùng native client vừa import.

**Lưu ý quan trọng:** thư mục game của instance nằm trong `GAME_HOME/instances/`, nhưng native version và metadata chọn version được Horizon lưu ở khu vực dữ liệu riêng. Vì vậy thư mục instance có thể chép thẳng vào `instances`, còn hai lệnh CLI là bước cần thiết để đăng ký native client và gắn nó với instance.

## 5. Bảo mật

Native mod là mã Rust chạy với quyền của người dùng, không được sandbox. Chỉ import binary và mod mà bạn tin cậy. Hãy thử khởi chạy trước khi dùng với thế giới quan trọng.

Windows và Linux x86_64 được cấu hình; macOS chưa được xác minh.
