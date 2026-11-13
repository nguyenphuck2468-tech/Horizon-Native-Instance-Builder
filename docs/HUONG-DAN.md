# Hướng dẫn sử dụng Horizon Native Instance Builder

Tài liệu này hướng dẫn chạy quy trình tạo native client từ Horizon, Minecraft game directory và các gói native mod `.hnmod`.

> **Lưu ý quan trọng về quyền riêng tư và bản quyền:** repo Builder hiện là public. Không tải Minecraft game ZIP lên Release công khai của repo này. Hãy lưu ZIP trong một repository GitHub **private** riêng, sau đó cấp quyền đọc thông qua secret `MINECRAFT_INPUTS_TOKEN`. Không commit game ZIP, token đăng nhập hoặc dữ liệu tài khoản vào Git.

## 1. Builder tạo ra những gì?

Workflow tạo hai bản build riêng:

- `native-build-linux-x86_64`: native client cho Linux 64-bit.
- `native-build-windows-x86_64`: native client cho Windows 64-bit.

Ngoài ra còn có artifact lưu bản Horizon instance ZIP gốc và báo cáo/log build. macOS hiện chưa phải target được xác minh.

Đây là quy trình thử nghiệm. CI xanh ở bước kiểm tra archive **không đồng nghĩa** native client đã build thành công hoặc chạy được trên máy người dùng. Cần một lần chạy native build thực tế với đầu vào hợp lệ để xác nhận.

## 2. Chuẩn bị ba loại đầu vào

### A. Horizon instance backup

Đây là bản sao dữ liệu instance của Horizon, có thể chứa cấu hình, world, log hoặc dữ liệu launcher. Nó **không thay thế** Minecraft game directory.

Có thể đặt tại:

- `input/instance/instance.zip` (tên ưu tiên), hoặc
- `input/instance/horizon.zip` (tên tương thích cũ).

Hoặc tải lên Release của repo Builder và điền `instance_release_tag` cùng `instance_asset_name` khi chạy workflow. ZIP gốc được giữ thành artifact riêng.

### B. Minecraft game directory ZIP

Đây là đầu vào riêng bắt buộc để chuẩn bị game. Hãy dùng một game directory hoàn chỉnh từ bản cài Minecraft hợp lệ, thường là thư mục `.minecraft` của profile/version bạn định build.

ZIP phải có cấu trúc game thực tế, tối thiểu gồm:

- `versions/<version>/<version>.json`
- `versions/<version>/<version>.jar` khớp metadata Mojang trong JSON
- `assets/indexes/` và các asset object được index tham chiếu
- `libraries/` có các JAR cần thiết

Có thể ZIP thư mục game trực tiếp hoặc ZIP thư mục cha chứa nó; bộ giải nén sẽ dò root dựa trên `versions/<version>/<version>.json`. Chỉ có manifest/overrides của Modrinth hoặc CurseForge, một bản Horizon backup, hoặc chỉ có file JSON mà thiếu client JAR/assets/libraries đều không đạt.

**Không đưa vào ZIP** các tệp thông tin đăng nhập như `launcher_accounts.json`, access token, session token, hoặc dữ liệu bí mật khác. Chỉ đưa các tệp game cần thiết. Không cần đóng gói cả thư mục Downloads hay toàn bộ hồ sơ Windows.

#### Lưu ZIP ở nơi riêng tư

1. Tạo một repository GitHub mới ở chế độ **Private**, ví dụ `minecraft-build-inputs`.
2. Tạo một Release trong repository private đó.
3. Đính kèm ZIP với tên `minecraft.zip` (hoặc tên khác nếu sẽ nhập đúng tên ở workflow).
4. Ghi lại tag Release, ví dụ `mc-input-1`.

Không dùng Release công khai của repo Builder để phát tán file game. Người chạy build phải có quyền truy cập hợp pháp vào các tệp đầu vào.

#### Cấp quyền đọc cho workflow

Trong repo private chứa ZIP:

1. Tạo Fine-grained Personal Access Token chỉ cấp quyền **Contents: Read-only** cho đúng repository chứa asset.
2. Trong repo Builder, mở **Settings → Secrets and variables → Actions → New repository secret**.
3. Đặt tên secret là `MINECRAFT_INPUTS_TOKEN`, giá trị là token vừa tạo.
4. Không ghi token vào file, commit, workflow input hoặc log.

Token chỉ được dùng ở job tải Release asset; workflow không chuyển token vào tiến trình native build. Nếu không muốn tạo token, chỉ có thể tải từ Release mà `GITHUB_TOKEN` của workflow đã có quyền đọc.

### C. Native mod bundles

Đặt một hoặc nhiều file `.hnmod` tại `input/mods/`, ví dụ:

```text
input/
  mods/
    example-mod.hnmod
    another-mod.hnmod
```

Chỉ dùng mod bạn tin tưởng và đã kiểm tra nguồn. `.hnmod` chứa native code, không chạy trong sandbox; mod độc hại có thể thực thi mã trên runner trong lúc build.

## 3. Chạy GitHub Actions

1. Mở repository [Horizon-Native-Instance-Builder](https://github.com/nguyenphuck2468-tech/Horizon-Native-Instance-Builder).
2. Chọn tab **Actions**.
3. Chọn workflow **Build Horizon Native Instance**.
4. Nhấn **Run workflow** và chọn branch `main`.
5. Điền các trường:

| Trường | Giá trị |
|---|---|
| `horizon_revision` | Nhánh, tag hoặc commit Horizon cần build; mặc định `main` |
| `instance_release_tag` | Tag Release của Horizon backup nếu tải từ Release; để trống nếu ZIP đã có trong repo |
| `instance_asset_name` | Tên asset Horizon backup, thường là `instance.zip` |
| `minecraft_release_tag` | Tag Release bắt buộc chứa Minecraft game ZIP |
| `minecraft_source_repository` | `owner/repo` của repository chứa Minecraft ZIP; để trống nếu dùng repo Builder |
| `minecraft_asset_name` | Tên asset game ZIP, mặc định `minecraft.zip` |

6. Nhấn **Run workflow** để bắt đầu.

Nếu dùng repository private riêng, `minecraft_source_repository` phải là `owner/repo` chính xác và secret `MINECRAFT_INPUTS_TOKEN` phải có quyền đọc repository đó.

## 4. Đọc kết quả

Workflow chạy theo các chặng:

1. Kiểm tra cấu trúc, giới hạn kích thước, đường dẫn ZIP và các gói mod.
2. Kiểm tra Minecraft version metadata, client JAR theo SHA-1, asset index và asset object.
3. Chạy native build trên runner Linux và Windows độc lập.
4. Yêu cầu file native client thực tế phải tồn tại; chỉ build được launcher CLI không được tính là thành công.

Khi run hoàn tất, mở phần **Artifacts** ở cuối trang Actions và tải artifact tương ứng với hệ điều hành. Nếu một target thất bại, tải log của target đó để xem lỗi cụ thể; không dùng artifact thiếu file client.

## 5. Import native client vào Horizon

Trên máy người dùng, cần có Horizon base release tương thích đã được cài và chuẩn bị. Giải nén artifact đúng hệ điều hành, tìm file:

- Windows: `horizon-client.exe`
- Linux: `horizon-client`

Sau đó chạy lệnh import bằng Horizon Launcher CLI:

```bash
horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned
```

Thay placeholder bằng đường dẫn thực tế. Cờ `--trust-unsigned` có nghĩa là người dùng chủ động tin binary chưa được ký; chỉ import binary do chính bạn build hoặc đã kiểm tra. Lệnh import sử dụng game files từ Horizon base release đã cài trên máy để tạo version native riêng.

Nếu cần khôi phục world/cấu hình từ Horizon backup, import `horizon-instance-zip` riêng qua luồng import instance của Horizon. Không nhầm artifact backup với native client.

## 6. Xử lý lỗi thường gặp

| Thông báo / hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| `The Horizon instance backup is not a Minecraft game install` | Thiếu `input/minecraft/minecraft.zip` hoặc tag Release không có asset. Cung cấp Minecraft game ZIP riêng; Horizon backup không thay thế được. |
| `minecraft_release_tag` không được điền | Đây là input bắt buộc. Chọn tag Release đang chứa asset Minecraft ZIP. |
| Không tải được private Release | Kiểm tra `minecraft_source_repository`, secret `MINECRAFT_INPUTS_TOKEN`, và quyền Contents: Read-only. |
| Thiếu `versions/<id>/<id>.json` | ZIP không chứa game directory đúng cấu trúc; tạo lại từ thư mục game đầy đủ. |
| Thiếu hoặc SHA-1 client JAR không khớp | Tệp JAR bị thiếu, hỏng hoặc không tương ứng với version JSON; tải lại game files bằng launcher chính thức. |
| Thiếu asset object hoặc library JAR | ZIP chưa đầy đủ; bổ sung các thư mục `assets` và `libraries` đúng với version đã chọn. |
| Archive bị từ chối vì path collision, symlink hoặc traversal | Không sửa validator để bỏ qua. Tạo lại ZIP sạch từ thư mục game, loại bỏ symlink/junction và tên đường dẫn bất thường. |
| Validate thành công nhưng native build thất bại | Xem log target Linux/Windows. Kiểm tra Horizon revision, native mod và các phụ thuộc của runner. Validate đầu vào không bảo đảm native mod tương thích. |
| Có artifact nhưng không import/chạy được | Xác nhận đã tải đúng target, Horizon base tương thích và binary được tạo từ cùng bộ đầu vào. Báo lỗi kèm build report/log; không coi compile thành công là xác nhận runtime. |

## 7. Giới hạn hiện tại

- Targets được cấu hình: Linux x86_64 và Windows x86_64.
- macOS chưa được xác minh.
- Workflow không đăng nhập tài khoản Minecraft và không tải game từ tài khoản người dùng.
- Workflow không tự tạo Minecraft game ZIP hay cung cấp game files.
- Native mod là mã thực thi, không phải plugin sandbox.
- Cần kiểm thử import và launch thực tế trên máy đích trước khi coi một bản build là ổn định.

