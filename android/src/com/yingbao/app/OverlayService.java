package com.yingbao.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
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
import android.view.animation.OvershootInterpolator;
import android.webkit.CookieManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.LinearLayout;

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
    public static final String ACTION_REFRESH_APPEARANCE = "com.yingbao.app.REFRESH_OVERLAY_APPEARANCE";
    public static final String ACTION_RESIZE = "com.yingbao.app.RESIZE_OVERLAY";
    private static volatile boolean running = false;

    private WindowManager windowManager;
    private FrameLayout overlayView;
    private ImageView modelView;
    private TextView bubbleView;
    private LinearLayout quickMenu;
    private WindowManager.LayoutParams params;
    private WindowManager.LayoutParams bubbleParams;
    private long idleStart;
    private boolean interacting = false;
    private ScaleGestureDetector scaleDetector;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Random random = new Random();
    private static final String[] LOCAL_REACTIONS = new String[]{
        "嗯？","干嘛呀","又戳我。","唔…","我在呢。","看着你呢。","别戳脸…","痒。","知道啦。","你很闲嘛…",
        "轻一点。","喂。","怎么啦？","我听着。","戳到了。","再戳？","哼。","有事就说。","在看你。","别闹。",
        "嗯哼？","被你发现了。","干什么嘛。","我没跑。","好啦好啦。","手拿开。","你故意的吧。","又是你。","我知道是你。","别一直点。",
        "唔嗯。","有点痒…","你想干嘛？","我在这。","看到你了。","别戳头发。","裙子别碰。","真拿你没办法。","一下就好。","还来？",
        "嗯——？","我回头了。","听到了。","别催嘛。","好，我看你。","怎么这么爱戳。","被戳到了。","小心一点。","我没生气。","就一下哦。"
    };

    private int modelWidthDp = 140;
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
        if (intent != null && ACTION_RESIZE.equals(intent.getAction()) && overlayView != null) {
            resizeOverlay(intent.getIntExtra("delta", 0));
        }
        if (intent != null && ACTION_REFRESH_APPEARANCE.equals(intent.getAction())) refreshAppearance();
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
            ch.setDescription("保持萤的桌面精灵运行");
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
        modelWidthDp = getSharedPreferences("ying_overlay", MODE_PRIVATE).getInt("width_dp", 140);

        overlayView = new FrameLayout(this);
        overlayView.setBackgroundColor(Color.TRANSPARENT);

        modelView = new ImageView(this);
        modelView.setImageResource(R.drawable.yingbao_model);
        modelView.setAdjustViewBounds(true);
        modelView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        modelView.setBackgroundColor(Color.TRANSPARENT);
        overlayView.addView(modelView, new FrameLayout.LayoutParams(-1, -1));

        bubbleView = new TextView(this);
        bubbleView.setTextSize(13);
        bubbleView.setTextColor(Color.rgb(91, 70, 80));
        bubbleView.setPadding(dp(10), dp(7), dp(10), dp(7));
        bubbleView.setGravity(Gravity.CENTER);
        bubbleView.setVisibility(View.GONE);
        GradientDrawable bubbleBg = new GradientDrawable();
        bubbleBg.setColor(Color.argb(245, 255, 248, 251));
        bubbleBg.setStroke(dp(1), Color.argb(90, 239, 127, 164));
        bubbleBg.setCornerRadius(dp(15));
        bubbleView.setBackground(bubbleBg);
        FrameLayout.LayoutParams bubbleLp = new FrameLayout.LayoutParams(
            dp(150), FrameLayout.LayoutParams.WRAP_CONTENT
        );
        bubbleLp.gravity = Gravity.TOP | Gravity.RIGHT;
        bubbleLp.topMargin = dp(2);
        bubbleLp.rightMargin = dp(2);
        // Speech lives in a separate, non-touchable window beside the pet.
        // Keeping it outside the model window prevents covering her face.

        quickMenu = new LinearLayout(this);
        quickMenu.setOrientation(LinearLayout.VERTICAL);
        quickMenu.setPadding(dp(5), dp(5), dp(5), dp(5));
        quickMenu.setVisibility(View.GONE);
        GradientDrawable menuBg = new GradientDrawable();
        menuBg.setColor(Color.argb(238, 247, 249, 254));
        menuBg.setCornerRadius(dp(15));
        quickMenu.setBackground(menuBg);
        addQuickAction("聊天", () -> { hideQuickMenu(); openMainApp(); });
        addQuickAction("缩小一点", () -> { resizeOverlay(-20); hideQuickMenu(); });
        addQuickAction("放大一点", () -> { resizeOverlay(20); hideQuickMenu(); });
        addQuickAction("收起悬浮窗", () -> { hideQuickMenu(); stopSelf(); });
        FrameLayout.LayoutParams menuLp = new FrameLayout.LayoutParams(dp(112), FrameLayout.LayoutParams.WRAP_CONTENT);
        menuLp.gravity = Gravity.CENTER;
        overlayView.addView(quickMenu, menuLp);

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
        bubbleParams = new WindowManager.LayoutParams(
            dp(164), WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
            PixelFormat.TRANSLUCENT
        );
        bubbleParams.gravity = Gravity.TOP | Gravity.LEFT;
        bubbleView.setMaxLines(4);
        idleStart = android.os.SystemClock.uptimeMillis();
        handler.post(idleRunnable);
        refreshAppearance();
        scheduleAmbientBubble();

        scaleDetector = new ScaleGestureDetector(this,
            new ScaleGestureDetector.SimpleOnScaleGestureListener() {
                @Override public boolean onScaleBegin(ScaleGestureDetector d) {
                    scaling = true;
                    handler.removeCallbacks(longPressRunnable);
                    return true;
                }
                @Override public boolean onScale(ScaleGestureDetector d) {
                    int next = (int)(modelWidthDp * d.getScaleFactor());
                    modelWidthDp = Math.max(90, Math.min(210, next));
                    params.width = dp(modelWidthDp);
                    params.height = dp(modelWidthDp * 3 / 2);
                    try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
                    return true;
                }
                @Override public void onScaleEnd(ScaleGestureDetector d) {
                    getSharedPreferences("ying_overlay", MODE_PRIVATE).edit().putInt("width_dp", modelWidthDp).apply();
                    handler.postDelayed(() -> scaling = false, 120);
                }
            });

        overlayView.setOnTouchListener((v, e) -> handleTouch(e));
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
                interacting = true;
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
                    positionBubble();
                }
                return true;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                handler.removeCallbacks(longPressRunnable);
                interacting = false;
                if (moved) settlePet();
                if (e.getActionMasked() == MotionEvent.ACTION_UP && !moved && !scaling && !longTriggered) {
                    if (quickMenu != null && quickMenu.getVisibility() == View.VISIBLE) hideQuickMenu();
                    else poke();
                }
                return true;
        }
        return true;
    }
    private void addQuickAction(String label, Runnable action) {
        TextView item = new TextView(this);
        item.setText(label);
        item.setTextSize(12);
        item.setTextColor(Color.rgb(55, 66, 91));
        item.setGravity(Gravity.CENTER);
        item.setPadding(dp(8), dp(8), dp(8), dp(8));
        item.setOnClickListener(v -> action.run());
        quickMenu.addView(item, new LinearLayout.LayoutParams(-1, -2));
    }

    private void showQuickMenu() {
        if (quickMenu != null) {
            bubbleView.setVisibility(View.GONE);
            quickMenu.setVisibility(View.VISIBLE);
        }
    }

    private void hideQuickMenu() {
        if (quickMenu != null) quickMenu.setVisibility(View.GONE);
    }

    private void resizeOverlay(int deltaDp) {
        modelWidthDp = Math.max(90, Math.min(210, modelWidthDp + deltaDp));
        params.width = dp(modelWidthDp);
        params.height = dp(modelWidthDp * 3 / 2);
        getSharedPreferences("ying_overlay", MODE_PRIVATE).edit().putInt("width_dp", modelWidthDp).apply();
        try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
        positionBubble();
    }

    private void openMainApp() {
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        startActivity(i);
    }

    private void poke() {
        lastPokeTime = android.os.SystemClock.uptimeMillis();
        // Local tactile feedback must never wait for network.
        long duration = random.nextBoolean() ? 500L : 800L;
        if (modelView != null) {
            modelView.animate().cancel();
            modelView.setScaleX(1f);
            modelView.setScaleY(1f);
            modelView.animate()
                .scaleX(1.06f).scaleY(1.06f)
                .setDuration(duration / 2)
                .setInterpolator(new OvershootInterpolator(1.4f))
                .withEndAction(() -> {
                    if (modelView != null) modelView.animate()
                        .scaleX(1f).scaleY(1f)
                        .setDuration(duration / 2)
                        .setInterpolator(new OvershootInterpolator(1.15f))
                        .start();
                }).start();
        }
        showBubble(LOCAL_REACTIONS[random.nextInt(LOCAL_REACTIONS.length)], 2600);
    }

    private void refreshAppearance() {
        new Thread(() -> {
            String pose = "stand";
            String outfit = "moon";
            try {
                JSONObject j = request("GET", "/api/mobile/appearance", null);
                pose = j.optString("pose", "stand");
                outfit = j.optString("outfit", "moon");
            } catch (Exception ignored) {}
            final Bitmap bitmap = loadRemoteBitmap("/assets/character/" + outfit + "/" + pose + ".webp");
            handler.post(() -> {
                if (modelView == null) return;
                if (bitmap != null) modelView.setImageBitmap(bitmap);
                else modelView.setImageResource(R.drawable.yingbao_model);
            });
        }).start();
    }

    private Bitmap loadRemoteBitmap(String path) {
        for (String base : NetConfig.ordered(this)) {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection)new URL(base + path).openConnection();
                c.setConnectTimeout(5000);
                c.setReadTimeout(9000);
                c.setUseCaches(true);
                String cookies = CookieManager.getInstance().getCookie(base);
                if (cookies != null && !cookies.isEmpty()) c.setRequestProperty("Cookie", cookies);
                if (c.getResponseCode() != 200) continue;
                try (InputStream in = c.getInputStream()) {
                    Bitmap b = BitmapFactory.decodeStream(in);
                    if (b != null) return b;
                }
            } catch (Exception ignored) {
            } finally {
                if (c != null) c.disconnect();
            }
        }
        return null;
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

    private final Runnable idleRunnable = new Runnable() {
        @Override public void run() {
            if (modelView != null && !interacting &&
                android.os.SystemClock.uptimeMillis() - lastPokeTime > 1100) {
                double t = (android.os.SystemClock.uptimeMillis() - idleStart) / 1000.0;
                modelView.setTranslationY(dp(2) * (float)Math.sin(t * 1.9));
                modelView.setRotation(0.9f * (float)Math.sin(t * 0.72));
                float breath = 1f + 0.008f * (float)Math.sin(t * 2.1);
                modelView.setScaleX(breath);
                modelView.setScaleY(breath);
            }
            handler.postDelayed(this, 40);
        }
    };
    private long lastPokeTime = 0;

    private void settlePet() {
        if (params == null || windowManager == null) return;
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        final int fromX = params.x, fromY = params.y;
        final int toX = Math.max(0, Math.min(fromX, dm.widthPixels - params.width));
        final int toY = Math.max(0, Math.min(fromY, dm.heightPixels - params.height));
        android.animation.ValueAnimator spring = android.animation.ValueAnimator.ofFloat(0f, 1f);
        spring.setDuration(320);
        spring.setInterpolator(new OvershootInterpolator(0.7f));
        spring.addUpdateListener(a -> {
            float v = (float)a.getAnimatedValue();
            params.x = fromX + Math.round((toX - fromX) * v);
            params.y = fromY + Math.round((toY - fromY) * v);
            try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
            positionBubble();
        });
        spring.start();
    }

    private void positionBubble() {
        if (bubbleParams == null || params == null || windowManager == null) return;
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        int gap = dp(6);
        int right = params.x + params.width + gap;
        bubbleParams.x = right + bubbleParams.width <= dm.widthPixels
            ? right : Math.max(0, params.x - bubbleParams.width - gap);
        bubbleParams.y = Math.max(0, Math.min(params.y + dp(42), dm.heightPixels - dp(110)));
        if (bubbleView != null && bubbleView.getParent() != null) {
            try { windowManager.updateViewLayout(bubbleView, bubbleParams); } catch (Exception ignored) {}
        }
    }

    private void showBubble(String text, long duration) {
        if (bubbleView == null) return;
        bubbleView.setText(text);
        bubbleView.setVisibility(View.VISIBLE);
        if (bubbleView.getParent() == null) {
            positionBubble();
            try { windowManager.addView(bubbleView, bubbleParams); } catch (Exception ignored) {}
        } else positionBubble();
        handler.removeCallbacks(hideBubbleRunnable);
        handler.postDelayed(hideBubbleRunnable, duration);
    }

    private final Runnable hideBubbleRunnable = new Runnable() {
        @Override public void run() {
            if (bubbleView != null) {
                bubbleView.setVisibility(View.GONE);
                if (bubbleView.getParent() != null && windowManager != null) {
                    try { windowManager.removeView(bubbleView); } catch (Exception ignored) {}
                }
            }
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
        if (bubbleView != null && bubbleView.getParent() != null && windowManager != null) {
            try { windowManager.removeView(bubbleView); } catch (Exception ignored) {}
        }
        if (windowManager != null && overlayView != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) {}
        }
        overlayView = null;
        modelView = null;
        bubbleView = null;
        super.onDestroy();
    }
}
