package com.jiangli.fcmreconnect;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;

public final class HeartbeatSender {
    private static final String ACTION_MCS = "com.google.android.intent.action.MCS_HEARTBEAT";
    private static final String ACTION_GTALK = "com.google.android.intent.action.GTALK_HEARTBEAT";
    private static final String GMS = "com.google.android.gms";
    private static final String GSF = "com.google.android.gsf";

    private HeartbeatSender() {}

    public static int send(Context context) {
        int sent = 0;
        sent += sendTo(context, ACTION_MCS, GMS);
        sent += sendTo(context, ACTION_GTALK, GMS);
        sent += sendTo(context, ACTION_MCS, GSF);
        sent += sendTo(context, ACTION_GTALK, GSF);

        context.getSharedPreferences("fcm_reconnect", Context.MODE_PRIVATE)
                .edit()
                .putLong("last_heartbeat", System.currentTimeMillis())
                .putInt("last_broadcast_count", sent)
                .apply();
        return sent;
    }

    private static int sendTo(Context context, String action, String pkg) {
        try {
            Intent intent = new Intent(action);
            intent.setPackage(pkg);
            context.sendBroadcast(intent);
            return 1;
        } catch (Exception ignored) {
            return 0;
        }
    }

    public static boolean openDiagnostics(Context context) {
        try {
            Intent intent = new Intent();
            intent.setComponent(new ComponentName(
                    GMS,
                    "com.google.android.gms.gcm.GcmDiagnostics"
            ));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }
}
