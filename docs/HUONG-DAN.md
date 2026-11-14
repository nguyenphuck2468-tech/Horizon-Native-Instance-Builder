# Hướng dẫn sử dụng Horizon Native Instance Builder

Builder hiện có thể **tự tải Minecraft trực tiếp từ Mojang**. Bạn không cần tự tìm minecraft.zip, không cần tải riêng minecraft-26.3-client.jar, cũng không cần tự gom assets và libraries.

## 1. Builder tạo ra gì?

Workflow tạo native client cho:

- native-build-linux-x86_64: Linux 64-bit.
- native-build-windows-x86_64: Windows 64-bit.

Ngoài ra có artifact riêng giữ nguyên Horizon instance backup và log/báo cáo build. macOS chưa phải target đã xác minh.

## 2. Chuẩn bị đầu vào

### A. Horizon instance backup

Đây là ZIP dữ liệu Horizon (world, cấu hình, dữ liệu instance), không phải bộ cài Minecraft.

Đặt một trong hai tên:

- input/instance/instance.zip (ưu tiên).
- input/instance/horizon.zip (tương thích tên cũ).

Hoặc tải ZIP lên Release của repo Builder rồi nhập instance_release_tag và instance_asset_name.

### B. Minecraft — tự tải từ Mojang

Mặc định không cần chuẩn bị tệp nào. Mỗi runner Linux/Windows sẽ tự tải bộ Minecraft tương ứng từ manifest và máy chủ file chính thức của Mojang.

Các trường có thể chọn khi chạy workflow:

| minecraft_version | Ý nghĩa |
|---|---|
| latest-release | Bản phát hành ổn định mới nhất theo Mojang |
| latest-snapshot | Snapshot mới nhất theo Mojang |
| 26.3 | Tải đúng version 26.3 nếu version đó có trong manifest chính thức |

Downloader tự lấy:

- Version JSON và client JAR.
- Các library artifact và classifier được khai báo trong metadata.
- Asset index.
- Toàn bộ asset object mà index tham chiếu.

Từng tệp được đối chiếu kích thước và SHA-1 với metadata Mojang. Downloader chỉ chấp nhận HTTPS từ tên miền Mojang/Minecraft chính thức, kiểm tra đường dẫn an toàn và thử lại khi kết nối bị ngắt.

**Lưu ý:** workflow không đăng nhập tài khoản Microsoft/Minecraft. Nó lấy metadata và file công khai từ Mojang; người chạy vẫn phải có quyền sử dụng game theo điều khoản Minecraft.

### C. Dùng ZIP Minecraft có sẵn (tùy chọn tương thích cũ)

Chỉ dùng cách này nếu bạn đã có một game directory ZIP hoàn chỉnh. ZIP phải chứa versions/<version>/<version>.json, client JAR đúng SHA-1, assets/indexes, asset objects và libraries.

Không dùng riêng minecraft-26.3-client.jar làm toàn bộ ZIP: JAR chỉ là một phần của game directory.

Nếu ZIP nằm trong repository GitHub riêng tư:
1. Lưu asset trong Release của repository private.
2. Tạo Fine-grained token chỉ có Contents: Read-only cho repository đó.
3. Lưu token thành Actions secret MINECRAFT_INPUTS_TOKEN trong repo Builder.

Không đưa game ZIP lên Release công khai. Khi dùng cách Mojang mặc định, không cần token này.

### D. Native mod bundles

Đặt các file .hnmod tại input/mods/. Chỉ sử dụng mod mà bạn tin tưởng: .hnmod chứa native code và có thể thực thi mã trên runner.

## 3. Chạy workflow

1. Mở [Horizon Native Instance Builder](https://github.com/nguyenphuck2468-tech/Horizon-Native-Instance-Builder).
2. Chọn Actions → Build Horizon Native Instance.
3. Nhấn Run workflow.
4. Chọn các giá trị:

| Trường | Giá trị |
|---|---|
| horizon_revision | Nhánh/tag/commit Horizon cần build |
| instance_release_tag | Để trống nếu ZIP đã nằm trong repo; nếu tải từ Release thì nhập tag |
| instance_asset_name | Tên ZIP backup, mặc định instance.zip |
| minecraft_version | Mặc định 26.3; version phải khớp research-lock.json của revision Horizon đã chọn |
| minecraft_release_tag | Để trống để tự tải Mojang; chỉ nhập nếu dùng ZIP Minecraft có sẵn |
| minecraft_source_repository | Chỉ cần cho ZIP từ repo khác |
| minecraft_asset_name | Tên ZIP có sẵn, mặc định minecraft.zip |

**Khuyến nghị:** để minecraft_release_tag trống và giữ minecraft_version là 26.3 khi build Horizon main. Nếu chọn revision Horizon khác, hãy nhập đúng minecraft.version trong research-lock.json của revision đó. Workflow sẽ tự kiểm tra và dừng nếu version trong ZIP không khớp.

## 4. Các bước build

Mỗi target runner thực hiện độc lập:

1. Kiểm tra Horizon instance ZIP và .hnmod.
2. Tải Minecraft từ Mojang (hoặc tải ZIP tương thích cũ).
3. Kiểm tra version metadata, client JAR, libraries, asset index và SHA-1 của assets.
4. Giải nén game files và gọi horizon-launcher prepare --minecraft.
5. Build native client và xác nhận binary thực tế tồn tại.

Minecraft ZIP chỉ tồn tại trong runner tạm thời; **không được upload thành artifact**. Như vậy repo public không vô tình phát tán bộ game đã tải.

## 5. Import vào Horizon

Tải artifact đúng hệ điều hành:

- Windows: horizon-client.exe.
- Linux: horizon-client.

Sau đó chạy lệnh:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

Chỉ import binary do bạn tự build hoặc đã kiểm tra. Horizon instance backup được cung cấp riêng để khôi phục world/cấu hình khi cần.

## 6. Xử lý lỗi

| Lỗi | Cách xử lý |
|---|---|
| Version không có trong Mojang manifest | Kiểm tra lại ID version; thử latest-release hoặc version chính xác đang được Mojang công bố |
| Không tải được manifest/metadata | Kiểm tra kết nối runner tới piston-meta.mojang.com; không tắt TLS hoặc chuyển sang mirror không rõ nguồn |
| SHA-1/kích thước không khớp | Downloader sẽ dừng thay vì dùng file hỏng; chạy lại workflow để tải lại |
| Thiếu asset hoặc library | Kiểm tra log download; không bỏ qua bước xác minh |
| ZIP Minecraft có sẵn không hợp lệ | Cung cấp full game directory ZIP; một client JAR đơn lẻ không đủ |
| Native build thất bại | Xem log của Linux/Windows target; xác minh Horizon revision và từng .hnmod |
| Build xong nhưng không chạy | Kiểm tra phiên bản Horizon base, target OS/CPU và import đúng binary |

## 7. Giới hạn và hướng phát triển

- Linux x86_64 và Windows x86_64 đang là hai target cấu hình.
- macOS cần workflow/runner và kiểm thử riêng.
- Việc tải game không thay thế đăng nhập tài khoản Minecraft khi chơi.
- Compile thành công chưa đồng nghĩa runtime đã ổn định; cần kiểm thử import và khởi chạy trên máy đích.
