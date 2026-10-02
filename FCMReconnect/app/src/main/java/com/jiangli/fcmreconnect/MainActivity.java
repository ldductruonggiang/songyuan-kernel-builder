package com.jiangli.fcmreconnect;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.format.DateFormat;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Date;

public class MainActivity extends Activity {
    private TextView status;
    private TextView lastHeartbeat;
    private Button toggle;
    private RadioGroup intervals;
    private boolean updatingUi = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private View buildUi() {
        int pad = dp(20);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, dp(28), pad, pad);

        TextView title = new TextView(this);
        title.setText("FCM Reconnect");
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        TextView sub = new TextView(this);
        sub.setText("Giữ kết nối Google FCM trên ROM China bằng heartbeat định kỳ.\nKhông root • Không ADB • Không quyền Internet");
        sub.setTextSize(15);
        sub.setPadding(0, dp(8), 0, dp(20));
        root.addView(sub);

        status = new TextView(this);
        status.setTextSize(18);
        status.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(status);

        lastHeartbeat = new TextView(this);
        lastHeartbeat.setTextSize(14);
        lastHeartbeat.setPadding(0, dp(6), 0, dp(18));
        root.addView(lastHeartbeat);

        TextView intervalLabel = new TextView(this);
        intervalLabel.setText("Chu kỳ heartbeat");
        intervalLabel.setTextSize(16);
        intervalLabel.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(intervalLabel);

        intervals = new RadioGroup(this);
        intervals.setOrientation(RadioGroup.HORIZONTAL);
        intervals.setGravity(Gravity.CENTER_VERTICAL);

        addIntervalButton(5);
        addIntervalButton(10);
        addIntervalButton(15);
        root.addView(intervals);

        intervals.setOnCheckedChangeListener((group, checkedId) -> {
            if (updatingUi) return;
            View v = group.findViewById(checkedId);
            if (!(v instanceof RadioButton)) return;
            int minutes = (Integer) v.getTag();
            if (HeartbeatScheduler.isEnabled(this)) {
                HeartbeatScheduler.start(this, minutes);
                toast("Đã đổi chu kỳ thành " + minutes + " phút");
            } else {
                getSharedPreferences("fcm_reconnect", Context.MODE_PRIVATE)
                        .edit().putInt("interval_minutes", minutes).apply();
            }
            refresh();
        });

        toggle = new Button(this);
        toggle.setAllCaps(false);
        toggle.setTextSize(17);
        LinearLayout.LayoutParams full = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        full.topMargin = dp(18);
        root.addView(toggle, full);
        toggle.setOnClickListener(v -> toggleFixer());

        Button now = new Button(this);
        now.setText("Gửi heartbeat ngay");
        now.setAllCaps(false);
        root.addView(now, full);
        now.setOnClickListener(v -> {
            int count = HeartbeatSender.send(this);
            refresh();
            toast(count > 0 ? "Đã gửi heartbeat" : "Không gửi được heartbeat");
        });

        Button diag = new Button(this);
        diag.setText("Mở FCM Diagnostics");
        diag.setAllCaps(false);
        root.addView(diag, full);
        diag.setOnClickListener(v -> {
            if (!HeartbeatSender.openDiagnostics(this)) {
                toast("Máy này không mở được GcmDiagnostics trực tiếp. Hãy quay *#*#426#*#* trong app Điện thoại.");
            }
        });

        TextView note = new TextView(this);
        note.setText("Lưu ý\n• App không thể đọc trạng thái socket FCM bằng API công khai, nên heartbeat được gửi theo chu kỳ.\n• Nếu ROM đưa app vào ngủ sâu, chu kỳ 5 phút có thể bị Android trì hoãn.\n• Sau khi reboot máy, hãy mở app và bật lại để giữ đúng tiêu chí không xin quyền khởi động cùng hệ thống.\n• Hiệu quả cần kiểm tra thực tế bằng FCM Diagnostics và độ trễ thông báo.");
        note.setTextSize(13);
        note.setPadding(0, dp(22), 0, dp(16));
        root.addView(note);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        return scroll;
    }

    private void addIntervalButton(int minutes) {
        RadioButton rb = new RadioButton(this);
        rb.setId(View.generateViewId());
        rb.setText(minutes + " phút");
        rb.setTag(minutes);
        intervals.addView(rb);
    }

    private void toggleFixer() {
        if (HeartbeatScheduler.isEnabled(this)) {
            HeartbeatScheduler.stop(this);
            toast("Đã tắt FCM Reconnect");
        } else {
            int minutes = selectedInterval();
            HeartbeatSender.send(this);
            HeartbeatScheduler.start(this, minutes);
            toast("Đã bật • " + minutes + " phút");
        }
        refresh();
    }

    private int selectedInterval() {
        int id = intervals.getCheckedRadioButtonId();
        View v = intervals.findViewById(id);
        if (v instanceof RadioButton && v.getTag() instanceof Integer) {
            return (Integer) v.getTag();
        }
        return HeartbeatScheduler.getInterval(this);
    }

    private void refresh() {
        boolean enabled = HeartbeatScheduler.isEnabled(this);
        int interval = HeartbeatScheduler.getInterval(this);
        status.setText(enabled ? "● Đang bật • " + interval + " phút" : "○ Đang tắt");
        toggle.setText(enabled ? "Tắt FCM Reconnect" : "Bật FCM Reconnect");

        updatingUi = true;
        for (int i = 0; i < intervals.getChildCount(); i++) {
            View v = intervals.getChildAt(i);
            if (v instanceof RadioButton) {
                RadioButton rb = (RadioButton) v;
                rb.setChecked(((Integer) rb.getTag()) == interval);
            }
        }
        updatingUi = false;

        SharedPreferences p = getSharedPreferences("fcm_reconnect", Context.MODE_PRIVATE);
        long last = p.getLong("last_heartbeat", 0L);
        if (last == 0L) {
            lastHeartbeat.setText("Heartbeat gần nhất: chưa có");
        } else {
            String when = DateFormat.getDateFormat(this).format(new Date(last)) + " " +
                    DateFormat.getTimeFormat(this).format(new Date(last));
            lastHeartbeat.setText("Heartbeat gần nhất: " + when);
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }
}
