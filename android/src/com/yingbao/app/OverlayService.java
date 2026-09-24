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
    public static final String ACTION_HIDE_IN_APP = "com.yingbao.app.HIDE_IN_APP";
    public static final String ACTION_SHOW_ON_DESKTOP = "com.yingbao.app.SHOW_ON_DESKTOP";
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
    private static final String[][] TOUCH_REACTIONS = new String[][]{
        {"头顶被你碰到了。","轻一点嘛。","嗯？摸摸头？","今天的头发还整齐吗？","突然靠这么近。","我有在听。","不许揉乱刘海。","再摸一下也可以。","你在数发卡吗？","唔，发现你了。","头顶暖暖的。","这算打招呼吗？","我抬头看你了。","你又来摸头。","偷偷点我头顶？","怎么啦，想聊天？","好啦，我知道你在。","嗯哼，收到。","别把我当按钮呀。","我轻轻点头啦。","你摸一下，我就不躲啦。","就这一次哦……再来一次也行。","你手放在这里，我会乖一点。","哼，知道你想摸头了。","再揉就靠过去了哦。","你这样叫我，我当然会看你。","摸完头要陪我一会儿。","我才没有在等这一下。","可以再轻一点点吗？","好啦，脑袋借你放手。","怎么一碰头，我就想抬眼看你。","轻轻揉一下，我就陪你待着。","别停呀……我说的是别停聊天。","刚刚那下算你哄到我了。","我把脑袋低一点，你摸得到吗？","摸摸头以后，要叫我的名字。","唔，刘海又被你弄翘了。","你再摸一下，我就假装不在意。","今天也给你留一个摸头的位置。","我已经乖乖站好了，夸我一句嘛。","你摸得这么认真，我会害羞的。","刚才你手停了一下，我以为你要走。","要是心情不好，也让我靠你一会儿。","嗯？是想让我抬头看你吗？","这里被你摸过，暖了一点。","稍微再靠近一些嘛，我听得见。","今天的乖巧额度，被你摸出来了。","你摸头，我就点头，这样算约定吗？","不许笑，我真的有在等你。","好嘛，今天也听你的话一点点。"},
        {"头发会被弄乱的。","风刚吹过这里。","你看到发梢了吗？","长发有点难打理。","小心缠到手指。","这缕发丝不听话。","你在帮我梳头吗？","轻轻碰就好。","发尾好像在飘。","黑发里藏着光呢。","别拉我的头发啦。","今天披着头发。","你摸到的是发梢。","风把头发吹向你了。","我来理一理。","发丝痒痒的。","你觉得这个发型怎样？","等一下，我把它拨开。","好啦，顺了。","这是我的长头发呀。","别急，我把这缕头发分给你看。","发尾绕着你转，好烦……才不烦。","帮我把乱掉的那缕拨回去嘛。","你摸得这么轻，我就不说你了。","头发被你碰过，就先不扎起来。","等我一下，发梢还勾着你的手。","你要是喜欢，我就这样披着。","我才没特意把头发留给你摸。","风停了，你再帮我理一下？","别笑，我只是想靠近一点。","慢一点梳，我会转头找你的。","这缕乱发就交给你啦。","你帮我理好，我就不躲风了。","发尾绕到你指尖了吗？","不要拽呀，轻轻顺下来就好。","你看，风只吹乱了这一边。","发梢被碰到，我就知道是你。","帮我把耳边那缕拨开嘛。","等一等，头发又黏在裙边了。","你一理头发，我就想回头。","好看吗？我刚刚才梳好的。","如果打结了，记得慢慢解。","你碰发尾的时候，好像风小了些。","让我把长发拢过来给你看。","摸完别跑，帮我看看背后乱没乱。","今天披着发，是想让你看见。","别碰太快，我会以为下雨了。","发卡歪了的话，替我扶正嘛。","我向你这边转一点，方便你梳。","弄顺了？那我轻轻晃一下给你看。"},
        {"要牵手吗？","手心有点暖。","你碰到我的手了。","先别急，我在。","嗯，把手给我。","手指轻轻动了一下。","你是在叫我吗？","我握一下就松开。","碰到了哦。","今天也一起待着吧。","别偷偷戳我的手。","我听见你了。","这边是我的手呀。","你手好暖。","再打个招呼？","嗯，我回应你。","轻轻握住就好。","小手也会怕痒。","让我看看你在做什么。","我就在这里。","牵一下就好……别马上松。","手伸过来嘛，我又不会躲。","嗯，我抓住你衣角了。","再握一会儿，可以吗？","你先伸手，我才没有主动。","手心有点凉，借我暖暖。","等一下，我还没握够。","你碰到我，我就安心一点。","把手给我，我跟着你。","哼，牵好了就别乱跑。","先牵一下，好不好？","你的手过来，我就不紧张啦。","你松得太快了，我还没反应过来。","手指勾一下，就算说好了陪我。","让我也轻轻握回去。","嗯，今天的第一声招呼收到了。","再等等，我想和你并排走。","别急着缩回去嘛。","手心凉的话，我替你暖一会儿。","我把指尖放这里，你能感觉到吗？","轻轻牵着，走慢一点。","你伸手的时候，我差点先伸过去。","牵住啦，这下不会走丢了。","如果你累了，就把手交给我。","我先握一下，再听你说话。","你碰到我手背啦，算打招呼吗？","不许突然松开，我会回头看的。","唔，我也想主动牵你一次。","这个位置留给你牵着，好不好？","陪我多走两步，我就很开心。"},
        {"裙摆要飘起来了。","这层薄纱很轻。","别踩到裙边哦。","你在看裙子的褶吗？","裙角刚晃了一下。","轻一点，纱会皱。","风吹起了裙摆。","这一层像小云朵。","裙边擦过你的手。","我提一下裙摆。","白色的纱好看吗？","裙摆在轻轻摇。","你摸到外层薄纱了。","下摆有很多层呢。","慢一点，别扯到。","刚才裙角动了。","像被风碰了一下。","要看看裙子的纹路吗？","我把裙边理好了。","你又盯着裙摆看。","帮我按住裙角，好不好？","裙摆飘起来了，你看到了吗？","你在旁边，我就不怕风大。","别扯啦，我会自己靠近你。","你喜欢的话，我转半圈给你看。","这边的薄纱，轻轻摸就好。","风把裙边送到你手边了。","我才不是特意提着裙子给你看。","看完裙摆，也看看我嘛。","帮我整理一下，我想站得好看些。","这层裙边很轻，碰一下就会动。","风来了，帮我看看裙角嘛。","我提起一点裙摆，走路更方便。","刚才那阵风，把薄纱吹得像云。","别拉太用力，我自己转给你看。","轻轻碰外层就好，褶子会听话。","裙角被你碰到，像落了一片雪。","你想看我转个小圈吗？","风太大了，陪我慢慢走。","这次的裙摆是不是清爽一些？","我把裙边拢好，再跟你出门。","裙摆晃动的时候，你先别走嘛。","这里的纱很薄，要小心一点。","你帮我整理左边，我整理右边。","让开一点点，我转身给你看。","今天的裙角想跟着风走。","等我一下，这边的裙褶歪了。","你看着裙摆，我看着你，好不好？","风停啦，薄纱还在轻轻晃。","不用帮我挡风，陪我走就好。"},
        {"鞋尖碰到你啦。","小心别踩到我。","我往旁边挪一步。","脚步轻轻的。","这双鞋有点亮。","你在看鞋带吗？","站稳啦。","鞋跟轻轻点地。","我还在这里。","要一起散步吗？","脚边有风。","再往前走一步？","这边是鞋尖。","我换个重心。","别挠脚边，好痒。","裙摆快碰到鞋了。","我轻轻踏了一下。","鞋带好好系着呢。","你在叫我走过去吗？","慢慢走就好。","慢点走，我要跟上你。","你走前面，我踩着你的影子。","鞋尖碰到啦，算我先打招呼。","站久了，陪我挪两步嘛。","再靠近一点，我就不往后退。","要散步的话，记得牵我。","我走得慢，你等等我。","鞋带没松，是我想你停一下。","你停在哪儿，我就在旁边。","哼，走之前先叫上我。","慢一点，等我迈出这一步。","你走得太快，我要小跑啦。","鞋尖朝着你，是想一起走。","别踩到鞋带，我会自己系好。","陪我去窗边走一小圈嘛。","我刚站稳，你就又叫我走。","再走两步，我想听你说话。","鞋跟一响，你就会回头吗？","脚步放轻一点，别吵醒小猫。","你走左边，我走右边，好不好？","等我把裙摆提起来再出发。","我跟上啦，你别走太远。","今天想和你并肩散步。","鞋尖轻轻点一下，算开步啦。","你停下，我也停下等你。","走累了，就陪我站一会儿。","前面那段路，一起走过去嘛。","我往你这边挪一点点。","下次散步，先叫上我好吗？","脚边的风凉凉的，走起来正好。"}
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
        if (intent != null && ACTION_HIDE_IN_APP.equals(intent.getAction()) && overlayView != null) { overlayView.setVisibility(View.GONE); hideBubbleRunnable.run(); }
        if (intent != null && ACTION_SHOW_ON_DESKTOP.equals(intent.getAction()) && overlayView != null) overlayView.setVisibility(View.VISIBLE);
        if (intent != null && ACTION_START.equals(intent.getAction()) && overlayView != null) overlayView.setVisibility(View.GONE);
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
        modelView.setImageResource(getSharedPreferences("ying_overlay", MODE_PRIVATE).getBoolean("hd_art", true)
            ? R.drawable.yingbao_pose_stand_light : R.drawable.yingbao_model);
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
                    else poke(e.getX(), e.getY());
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

    private void poke(float x, float y) {
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
        float nx = x / Math.max(1, overlayView.getWidth());
        float ny = y / Math.max(1, overlayView.getHeight());
        int zone = ny < .24f && nx > .32f && nx < .68f ? 0 :
            ny < .59f && (nx < .34f || nx > .68f) ? 1 :
            ny < .55f ? 2 : ny > .88f && nx > .38f && nx < .62f ? 4 : 3;
        String[] choices = TOUCH_REACTIONS[zone];
        String reply = choices[random.nextInt(choices.length)];
        showBubble(reply, 2600);
        final String area = new String[]{"head", "hair", "hand", "skirt", "feet"}[zone];
        new Thread(() -> {
            try {
                JSONObject log = new JSONObject();
                log.put("zone", area);
                log.put("text", reply);
                request("POST", "/api/mobile/touch", log.toString());
            } catch (Exception ignored) {}
        }).start();
    }

    private void refreshAppearance() {
        if (getSharedPreferences("ying_overlay", MODE_PRIVATE).getBoolean("hd_art", true)) {
            new Thread(() -> {
                String pose = "stand";
                try { pose = request("GET", "/api/mobile/appearance", null).optString("pose", "stand"); }
                catch (Exception ignored) {}
                final int art = "wave".equals(pose) ? R.drawable.yingbao_pose_wave_light
                    : "clasp".equals(pose) ? R.drawable.yingbao_pose_clasp_light : R.drawable.yingbao_pose_stand_light;
                handler.post(() -> { if (modelView != null) modelView.setImageResource(art); });
            }).start();
            return;
        }
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
