package com.jiangli.fcmreconnect;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class HeartbeatReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!HeartbeatScheduler.isEnabled(context)) return;
        HeartbeatSender.send(context.getApplicationContext());
        HeartbeatScheduler.scheduleNext(context.getApplicationContext());
    }
}
