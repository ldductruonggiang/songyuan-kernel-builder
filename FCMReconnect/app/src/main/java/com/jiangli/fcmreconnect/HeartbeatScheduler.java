package com.jiangli.fcmreconnect;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;

public final class HeartbeatScheduler {
    private static final String PREFS = "fcm_reconnect";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_INTERVAL = "interval_minutes";
    private static final int REQUEST_CODE = 426;

    private HeartbeatScheduler() {}

    public static void start(Context context, int minutes) {
        if (minutes != 5 && minutes != 10 && minutes != 15) minutes = 10;
        prefs(context).edit()
                .putBoolean(KEY_ENABLED, true)
                .putInt(KEY_INTERVAL, minutes)
                .apply();
        scheduleNext(context, minutes);
    }

    public static void stop(Context context) {
        prefs(context).edit().putBoolean(KEY_ENABLED, false).apply();
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarm != null) alarm.cancel(pendingIntent(context));
    }

    public static void scheduleNext(Context context) {
        if (!isEnabled(context)) return;
        scheduleNext(context, getInterval(context));
    }

    private static void scheduleNext(Context context, int minutes) {
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarm == null) return;

        long triggerAt = SystemClock.elapsedRealtime() + minutes * 60_000L;
        PendingIntent pi = pendingIntent(context);

        // No exact-alarm permission needed. Android/HyperOS may defer this during deep Doze.
        alarm.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pi);
    }

    private static PendingIntent pendingIntent(Context context) {
        Intent intent = new Intent(context, HeartbeatReceiver.class);
        intent.setAction("com.jiangli.fcmreconnect.HEARTBEAT");
        return PendingIntent.getBroadcast(
                context,
                REQUEST_CODE,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean isEnabled(Context context) {
        return prefs(context).getBoolean(KEY_ENABLED, false);
    }

    public static int getInterval(Context context) {
        return prefs(context).getInt(KEY_INTERVAL, 10);
    }
}
