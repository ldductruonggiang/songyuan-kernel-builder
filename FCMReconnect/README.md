# FCM Reconnect

Ứng dụng Android rootless cực nhẹ để thử giảm trễ thông báo FCM trên ROM China/HyperOS bằng cách gửi heartbeat nội bộ cho Google Play services theo chu kỳ 5 / 10 / 15 phút.

## Đặc điểm
- Không root, không ADB, không Shizuku.
- Không khai báo quyền `INTERNET`.
- Không có quyền runtime.
- Không Firebase SDK, không analytics, không server, không telemetry.
- Gửi explicit broadcast `MCS_HEARTBEAT` và `GTALK_HEARTBEAT` đến `com.google.android.gms` / `com.google.android.gsf`.
- Nút mở `com.google.android.gms.gcm.GcmDiagnostics` để kiểm tra FCM.
- Dùng `AlarmManager.setAndAllowWhileIdle()` nên không cần quyền Exact Alarm.

## Giới hạn quan trọng
Android không cung cấp API công khai cho app thường để đọc đáng tin cậy trạng thái socket FCM của toàn hệ thống. Vì vậy bản này không giả vờ "detect Disconnect"; nó gửi heartbeat định kỳ. Nếu socket đã stale, Google Play services có cơ hội phát hiện và tự reconnect.

Không có permission boot để đúng tiêu chí "không xin quyền", vì vậy sau reboot hãy mở app và bật lại. Khi máy vào Doze sâu, Android/HyperOS có thể dời alarm; chu kỳ 5 phút không được đảm bảo tuyệt đối.

## Build
Mở bằng Android Studio (JDK 17), Sync Gradle rồi Build APK.

Workflow GitHub Actions của branch này sẽ tạo APK debug có thể cài trực tiếp.

## Kiểm tra
1. Mở app Điện thoại, nhập `*#*#426#*#*` hoặc bấm `Mở FCM Diagnostics` trong app.
2. Quan sát FCM/MCS trước và sau khi bật FCM Reconnect.
3. So sánh độ trễ thông báo ngân hàng / app FCM với một máy Global ROM.

## Quyền riêng tư
Source code hoàn toàn local. Không có mã gửi dữ liệu ra Internet.
