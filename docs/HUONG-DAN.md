# Hướng dẫn Horizon Native Instance Builder

Builder sẽ tạo bản Horizon native mới nhất cho Windows và Linux, kèm các native mod .hnmod mới nhất đã được kiểm tra tương thích với Nightly tương ứng. Máy của bạn không phải tự biên dịch.

## 1. Instance của bạn được giữ nguyên

Đặt backup Horizon tại:

- input/instance/instance.zip (khuyến nghị), hoặc
- input/instance/horizon.zip (tên cũ vẫn được hỗ trợ).

Đây là **dữ liệu instance Horizon**: thế giới, cấu hình, dữ liệu người chơi và thiết lập. Builder kiểm tra ZIP, giữ nguyên byte-for-byte và đưa nó vào gói kết quả. Builder không coi ZIP này là bộ cài Java, không chuyển đổi nó thành profile launcher khác và không ghi đè thế giới của bạn.

Nếu backup nằm trong Release của repo, nhập instance_release_tag và instance_asset_name khi chạy workflow.

## 2. Mod được cập nhật tự động

Các file .hnmod cũ trong input/mods/ được giữ lại làm bản dự phòng và để đối chiếu. Chúng không còn là bộ mod dùng cho bản build mới.

Khi chạy, workflow sẽ:

1. Lấy commit bất biến của Horizon Nightly chính thức hiện tại.
2. Đọc registry chính thức horizon-rust/horizon-mods.
3. Đọc báo cáo native-health được tạo cho đúng Nightly đó.
4. Tải phiên bản mới nhất của các mod đã chọn, kiểm tra SHA-256, kích thước và manifest bên trong .hnmod.
5. Bỏ qua mod nếu báo cáo chính thức đánh dấu phiên bản mới nhất của nó bị lỗi trên Nightly đó.
6. Dừng nếu báo cáo tương thích thuộc revision khác hoặc đã cũ, thay vì cố cài một bản không được xác nhận.

Danh sách mod được cập nhật:

- AppleSkin
- The Basic HUD
- Fast Items
- Freecam+
- Freelook
- Fullbright
- Jade
- JEI
- Mod Menu
- Zoom

Không phải lúc nào cũng có thể dùng cả 10 mod trên Nightly mới nhất. Nếu một mod chưa tương thích, báo cáo registry-mods.json sẽ ghi rõ lý do và mod đó không được ép cài. Các mod còn lại vẫn được build nếu bộ mod được chọn hợp lệ.

## 3. Runtime Horizon

Instance backup và runtime Horizon là hai thứ riêng biệt.

Horizon là client viết bằng Rust; builder tải dữ liệu runtime cần thiết từ Mojang để chuẩn bị Nightly. Phần tải này **không biến instance backup thành một bản cài Minecraft Java**, cũng không thay thế hay sửa thế giới trong backup.

Mặc định workflow tải runtime version 26.3 từ Mojang, kiểm tra metadata, thư viện và assets, rồi giữ các file tải về trong runner tạm thời. Chúng không được phát hành thành artifact công khai.

## 4. Chạy build

1. Mở [repo Horizon Native Instance Builder](https://github.com/nguyenphuck2468-tech/Horizon-Native-Instance-Builder).
2. Chọn **Actions → Build Horizon Native Instance**.
3. Nhấn **Run workflow**.
4. Giữ minecraft_version là 26.3 nếu Nightly hiện tại vẫn dùng version này.
5. Để trống minecraft_release_tag để runner tự tải runtime từ Mojang.
6. Nếu instance đã có trong repo thì không cần nhập instance_release_tag.

Horizon commit và bộ mod tương thích được tự động xác định, không cần tự chọn revision.

## 5. Kết quả

Khi Linux và Windows đều build, workflow tạo:

- horizon-instance-windows-x86_64
- horizon-instance-linux-x86_64

Mỗi ZIP chứa:

- instance/instance.zip: backup Horizon gốc, giữ nguyên.
- native/<target>/horizon-client[.exe]: native client đã build với mod được chọn.
- mods/*.hnmod: đúng các gói mod đã dùng.
- build-manifest.json: commit, SHA-256 và kích thước.
- README-INSTALL.txt: hướng dẫn import.

Đây là gói kết hợp backup + native client, không phải định dạng instance mới để mở trực tiếp bằng double-click.

Sau khi giải nén:
1. Khôi phục/import instance/instance.zip bằng luồng instance của Horizon.
2. Import native client bằng lệnh:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

Chỉ import binary bạn tự build và tin cậy.

## 6. Bảo mật và kiểm tra

Native mod là mã Rust chạy với quyền của người dùng, không được sandbox. Registry review và SHA-256 giúp xác minh nguồn và tính toàn vẹn, nhưng không khiến mã native trở nên vô hại.

Nếu build thất bại, kiểm tra:
- registry-mods.json: các mod đã chọn và mod bị loại.
- native-build.log: lỗi áp dụng mixin hoặc biên dịch.
- build.txt: Horizon commit, native version và target.

Workflow không dùng --allow-version-mismatch; không phát hành bản core-only giả làm bản có mod. Hãy thử khởi chạy bản import trước khi dùng với thế giới quan trọng.
