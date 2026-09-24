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
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Random;

public class OverlayService extends Service {
    public static final String ACTION_START = "com.yingbao.app.START_OVERLAY";
    private static volatile boolean running = false;

    private WindowManager windowManager;
    private FrameLayout overlayView;
    private ImageView modelView;
    private TextView bubbleView;
    private WindowManager.LayoutParams params;
    private ScaleGestureDetector scaleDetector;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Random random = new Random();

    private int modelWidthDp = 180;
    private boolean moved = false;
    private boolean scaling = false;
    private boolean longTriggered = false;
    private float downRawX, downRawY;
    private int startX, startY;

    public static boolean isRunning() { return running; }

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

    @Override public IBinder onBind(Intent intent) { return null; }

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
            ch.setDescription("保持萤的透明悬浮模型运行");
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

        modelView = new ImageView(this);
        modelView.setImageResource(R.drawable.yingbao_model);
        modelView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        modelView.setBackgroundColor(Color.TRANSPARENT);
        overlayView.addView(modelView, new FrameLayout.LayoutParams(-1, -1));

        bubbleView = new TextView(this);
        bubbleView.setTextSize(13);
        bubbleView.setTextColor(Color.rgb(35, 48, 74));
        bubbleView.setPadding(dp(10), dp(7), dp(10), dp(7));
        bubbleView.setGravity(Gravity.CENTER);
        bubbleView.setVisibility(View.GONE);
        GradientDrawable bubbleBg = new GradientDrawable();
        bubbleBg.setColor(Color.argb(235, 248, 250, 255));
        bubbleBg.setCornerRadius(dp(15));
        bubbleView.setBackground(bubbleBg);
        FrameLayout.LayoutParams bubbleLp = new FrameLayout.LayoutParams(
            dp(150), FrameLayout.LayoutParams.WRAP_CONTENT
        );
        bubbleLp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        bubbleLp.topMargin = dp(4);
        overlayView.addView(bubbleView, bubbleLp);

        params = new WindowManager.LayoutParams(
            dp(modelWidthDp), dp(modelWidthDp * 3 / 2),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.LEFT;
        params.x = dp(12);
        params.y = dp(110);
        windowManager.addView(overlayView, params);

        scaleDetector = new ScaleGestureDetector(this,
            new ScaleGestureDetector.SimpleOnScaleGestureListener() {
                @Override public boolean onScaleBegin(ScaleGestureDetector d) {
                    scaling = true;
                    handler.removeCallbacks(longPressRunnable);
                    return true;
                }
                @Override public boolean onScale(ScaleGestureDetector d) {
                    int next = (int)(modelWidthDp * d.getScaleFactor());
                    modelWidthDp = Math.max(105, Math.min(320, next));
                    params.width = dp(modelWidthDp);
                    params.height = dp(modelWidthDp * 3 / 2);
                    try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
                    return true;
                }
                @Override public void onScaleEnd(ScaleGestureDetector d) {
                    handler.postDelayed(() -> scaling = false, 120);
                }
            });

        overlayView.setOnTouchListener((v, e) -> handleTouch(e));
        scheduleAmbientBubble();
    }

    private final Runnable longPressRunnable = new Runnable() {
        @Override public void run() {
            if (!moved && !scaling) {
                longTriggered = true;
                openMainApp();
            }
        }
    };

    private boolean handleTouch(MotionEvent e) {
        scaleDetector.onTouchEvent(e);
        if (e.getPointerCount() > 1) {
            scaling = true;
            handler.removeCallbacks(longPressRunnable);
            return true;
        }
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                moved = false;
                longTriggered = false;
                downRawX = e.getRawX();
                downRawY = e.getRawY();
                startX = params.x;
                startY = params.y;
                handler.postDelayed(longPressRunnable, 800);
                return true;
            case MotionEvent.ACTION_MOVE:
                float dx = e.getRawX() - downRawX;
                float dy = e.getRawY() - downRawY;
                if (Math.hypot(dx, dy) > dp(10)) {
                    moved = true;
                    handler.removeCallbacks(longPressRunnable);
                    params.x = startX + (int)dx;
                    params.y = startY + (int)dy;
                    try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
                }
                return true;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                handler.removeCallbacks(longPressRunnable);
                if (e.getActionMasked() == MotionEvent.ACTION_UP && !moved && !scaling && !longTriggered) {
                    poke();
                }
                return true;
        }
        return true;
    }
    private void openMainApp() {
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        startActivity(i);
    }

    private void poke() {
        new Thread(() -> {
            String reply = null;
            try {
                JSONObject body = new JSONObject();
                body.put("area", "body");
                body.put("streak", 1);
                JSONObject out = request("POST", "/api/interaction/poke", body.toString());
                reply = out.optString("text", "");
            } catch (Exception ignored) {}
            if (reply == null || reply.trim().isEmpty()) reply = "嗯？";
            final String text = reply;
            handler.post(() -> showBubble(text, 4200));
        }).start();
    }

    private void scheduleAmbientBubble() {
        handler.removeCallbacks(ambientRunnable);
        long delay = 270000L + random.nextInt(60001);
        handler.postDelayed(ambientRunnable, delay);
    }

    private final Runnable ambientRunnable = new Runnable() {
        @Override public void run() {
            new Thread(() -> {
                try {
                    JSONObject out = request("GET", "/api/interaction/bubble", null);
                    String text = out.optString("text", "");
                    if (!text.isEmpty() && !"null".equals(text)) {
                        handler.post(() -> showBubble(text, 5000));
                    }
                } catch (Exception ignored) {}
                handler.post(OverlayService.this::scheduleAmbientBubble);
            }).start();
        }
    };

    private void showBubble(String text, long duration) {
        if (bubbleView == null) return;
        bubbleView.setText(text);
        bubbleView.setVisibility(View.VISIBLE);
        handler.removeCallbacks(hideBubbleRunnable);
        handler.postDelayed(hideBubbleRunnable, duration);
    }

    private final Runnable hideBubbleRunnable = new Runnable() {
        @Override public void run() {
            if (bubbleView != null) bubbleView.setVisibility(View.GONE);
        }
    };

    private JSONObject request(String method, String path, String body) throws Exception {
        Exception last = null;
        for (String base : NetConfig.ordered(this)) {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection)new URL(base + path).openConnection();
                c.setRequestMethod(method);
                c.setConnectTimeout(7000);
                c.setReadTimeout(25000);
                c.setUseCaches(false);
                c.setRequestProperty("Accept", "application/json");
                String cookies = CookieManager.getInstance().getCookie(base);
                if (cookies != null && !cookies.isEmpty()) c.setRequestProperty("Cookie", cookies);
                if (body != null) {
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    byte[] data = body.getBytes(StandardCharsets.UTF_8);
                    c.setFixedLengthStreamingMode(data.length);
                    try (OutputStream out = c.getOutputStream()) { out.write(data); }
                }
                int code = c.getResponseCode();
                InputStream raw = code >= 400 ? c.getErrorStream() : c.getInputStream();
                StringBuilder sb = new StringBuilder();
                if (raw != null) {
                    try (BufferedReader br = new BufferedReader(new InputStreamReader(raw, StandardCharsets.UTF_8))) {
                        String line; while ((line = br.readLine()) != null) sb.append(line);
                    }
                }
                if (code >= 400) throw new IllegalStateException("HTTP " + code);
                NetConfig.saveBase(this, base);
                return new JSONObject(sb.toString());
            } catch (Exception e) {
                last = e;
            } finally {
                if (c != null) c.disconnect();
            }
        }
        throw last != null ? last : new IllegalStateException("No endpoint available");
    }

    @Override
    public void onDestroy() {
        running = false;
        handler.removeCallbacksAndMessages(null);
        if (windowManager != null && overlayView != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) {}
        }
        overlayView = null;
        modelView = null;
        bubbleView = null;
        super.onDestroy();
    }
}
