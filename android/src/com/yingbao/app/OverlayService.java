package com.yingbao.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;

public class OverlayService extends Service {
    public static final String ACTION_START = "com.yingbao.app.START_OVERLAY";
    private static final String BASE = "https://38-76-190-23.sslip.io";
    private static volatile boolean running = false;

    private WindowManager windowManager;
    private FrameLayout overlayView;
    private WebView webView;
    private WindowManager.LayoutParams params;

    public static boolean isRunning() {
        return running;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        running = true;
        startAsForeground();
        if (Settings.canDrawOverlays(this)) showOverlay();
        else stopSelf();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (overlayView == null && Settings.canDrawOverlays(this)) showOverlay();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private int dp(int v) {
        return (int)(v * getResources().getDisplayMetrics().density + 0.5f);
    }
    private void startAsForeground() {
        String channelId = "yingbao_overlay";
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(
                channelId, "莹宝悬浮窗", NotificationManager.IMPORTANCE_LOW
            );
            ch.setDescription("保持萤的悬浮窗运行");
            nm.createNotificationChannel(ch);
        }

        Intent open = new Intent(this, MainActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        PendingIntent pi = PendingIntent.getActivity(
            this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Notification n = new Notification.Builder(this, channelId)
            .setContentTitle("莹宝")
            .setContentText("萤正在陪着你")
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setContentIntent(pi)
            .setOngoing(true)
            .build();

        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(9, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(9, n);
        }
    }
    private void showOverlay() {
        if (overlayView != null) return;
        windowManager = (WindowManager)getSystemService(WINDOW_SERVICE);
        overlayView = new FrameLayout(this);
        overlayView.setBackgroundColor(Color.TRANSPARENT);

        webView = new WebView(this);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        webView.setBackgroundColor(Color.TRANSPARENT);
        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new JsBridge(), "YingbaoAndroid");
        overlayView.addView(webView, new FrameLayout.LayoutParams(-1, -1));

        TextView drag = control("⋮⋮");
        FrameLayout.LayoutParams dragLp = new FrameLayout.LayoutParams(dp(42), dp(42));
        dragLp.gravity = Gravity.TOP | Gravity.LEFT;
        overlayView.addView(drag, dragLp);

        TextView close = control("×");
        FrameLayout.LayoutParams closeLp = new FrameLayout.LayoutParams(dp(42), dp(42));
        closeLp.gravity = Gravity.TOP | Gravity.RIGHT;
        overlayView.addView(close, closeLp);
        close.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { stopSelf(); }
        });
        params = new WindowManager.LayoutParams(
            dp(250), dp(420),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.LEFT;
        params.x = dp(16);
        params.y = dp(120);
        windowManager.addView(overlayView, params);

        drag.setOnTouchListener(new View.OnTouchListener() {
            private int startX, startY;
            private float downX, downY;
            @Override public boolean onTouch(View v, MotionEvent e) {
                if (e.getAction() == MotionEvent.ACTION_DOWN) {
                    startX = params.x;
                    startY = params.y;
                    downX = e.getRawX();
                    downY = e.getRawY();
                    return true;
                }
                if (e.getAction() == MotionEvent.ACTION_MOVE) {
                    params.x = startX + (int)(e.getRawX() - downX);
                    params.y = startY + (int)(e.getRawY() - downY);
                    windowManager.updateViewLayout(overlayView, params);
                    return true;
                }
                return false;
            }
        });
        webView.loadUrl(BASE + "/viewer?overlay=1");
    }

    private TextView control(String label) {
        TextView v = new TextView(this);
        v.setText(label);
        v.setTextSize(22);
        v.setTextColor(Color.WHITE);
        v.setGravity(Gravity.CENTER);
        v.setBackgroundColor(Color.argb(110, 8, 14, 28));
        return v;
    }

    private class JsBridge {
        @JavascriptInterface
        public void openMainApp() {
            Intent i = new Intent(OverlayService.this, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(i);
        }
    }

    @Override
    public void onDestroy() {
        running = false;
        if (windowManager != null && overlayView != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) { }
        }
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        overlayView = null;
        webView = null;
        super.onDestroy();
    }
}
