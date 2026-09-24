package com.yingbao.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

public class MainActivity extends Activity {
    private FrameLayout root;
    private WebView webView;
    private String deviceId;
    private boolean waitingOverlayPermission = false;
    private Button overlayButton;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Window w = getWindow();
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.BLACK);
        w.getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );
        deviceId = "android-" + Settings.Secure.getString(
            getContentResolver(), Settings.Secure.ANDROID_ID
        );
        CookieManager.getInstance().setAcceptCookie(true);
        NetConfig.syncExistingCookies();

        root = new FrameLayout(this);
        setContentView(root);
        checkSession();
    }

    private int dp(int value) {
        return (int)(value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private TextView text(String value, float size, int color) {
        TextView v = new TextView(this);
        v.setText(value);
        v.setTextSize(size);
        v.setTextColor(color);
        v.setGravity(Gravity.CENTER);
        return v;
    }

    private void showLoading() {
        root.removeAllViews();
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.rgb(13, 20, 37));
        box.addView(text("莹宝", 28, Color.WHITE));
        TextView sub = text("正在连接萤…", 14, Color.rgb(174, 185, 210));
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        sp.topMargin = dp(12);
        box.addView(sub, sp);
        root.addView(box, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));
    }

    private void checkSession() {
        showLoading();
        new Thread(new Runnable() {
            @Override public void run() {
                final int code = request("GET", "/api/mobile/whoami", null, false);
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        if (code == 200) showViewer();
                        else showLogin();
                    }
                });
            }
        }).start();
    }
    private void showLogin() {
        root.removeAllViews();
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        box.setPadding(dp(28), dp(72), dp(28), dp(28));
        box.setBackgroundColor(Color.rgb(13, 20, 37));

        ImageView icon = new ImageView(this);
        icon.setImageResource(com.yingbao.app.R.drawable.yingbao_icon);
        icon.setScaleType(ImageView.ScaleType.CENTER_CROP);
        LinearLayout.LayoutParams ip = new LinearLayout.LayoutParams(dp(132), dp(132));
        box.addView(icon, ip);

        TextView title = text("莹宝", 30, Color.WHITE);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(-2, -2);
        tp.topMargin = dp(22);
        box.addView(title, tp);

        TextView desc = text("第一次使用请输入你的专属密钥\n密钥验证后不会保存在软件里", 14, Color.rgb(174,185,210));
        desc.setLineSpacing(0, 1.25f);
        LinearLayout.LayoutParams dpv = new LinearLayout.LayoutParams(-1, -2);
        dpv.topMargin = dp(10);
        box.addView(desc, dpv);

        final EditText input = new EditText(this);
        input.setHint("YB-...");
        input.setSingleLine(true);
        input.setTextColor(Color.WHITE);
        input.setHintTextColor(Color.rgb(120,130,150));
        input.setBackgroundColor(Color.rgb(24,34,58));
        input.setPadding(dp(14), 0, dp(14), 0);
        LinearLayout.LayoutParams ep = new LinearLayout.LayoutParams(-1, dp(52));
        ep.topMargin = dp(28);
        box.addView(input, ep);

        final Button bind = new Button(this);
        bind.setText("绑定这台手机");
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(-1, dp(52));
        bp.topMargin = dp(14);
        box.addView(bind, bp);

        bind.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                String key = input.getText().toString().trim();
                if (key.length() < 10) {
                    Toast.makeText(MainActivity.this, "密钥不对哦", Toast.LENGTH_SHORT).show();
                    return;
                }
                bind.setEnabled(false);
                bind.setText("正在绑定…");
                bindDevice(key, input, bind);
            }
        });

        root.addView(box, new FrameLayout.LayoutParams(-1, -1));
    }
    private void bindDevice(final String key, final EditText input, final Button button) {
        new Thread(new Runnable() {
            @Override public void run() {
                String body = "{\"device_id\":\"" + json(deviceId) +
                    "\",\"access_key\":\"" + json(key) + "\"}";
                final int code = request("POST", "/api/mobile/bind", body, true);
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        input.setText("");
                        if (code == 200) {
                            Toast.makeText(MainActivity.this, "绑定成功", Toast.LENGTH_SHORT).show();
                            showViewer();
                        } else {
                            button.setEnabled(true);
                            button.setText("绑定这台手机");
                            String msg = code == 409 ? "这把密钥或这台设备已经绑定" : "密钥无效";
                            Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show();
                        }
                    }
                });
            }
        }).start();
    }

    private void showViewer() {
        root.removeAllViews();
        setupWebView();
        webView.loadUrl(NetConfig.getBase(this) + "/viewer?v=290");
    }

    private void setupWebView() {
        webView = new WebView(this);
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setCacheMode(WebSettings.LOAD_NO_CACHE);
        ws.setLoadsImagesAutomatically(true);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new NativeBridge(), "YingbaoNative");
        root.addView(webView, new FrameLayout.LayoutParams(-1, -1));
    }

    private class NativeBridge {
        @JavascriptInterface
        public void toggleOverlay() {
            runOnUiThread(() -> MainActivity.this.toggleOverlay());
        }

        @JavascriptInterface
        public boolean overlayRunning() {
            return OverlayService.isRunning();
        }

        @JavascriptInterface
        public void resizeOverlay(int delta) {
            if (!OverlayService.isRunning()) return;
            Intent i = new Intent(MainActivity.this, OverlayService.class);
            i.setAction(OverlayService.ACTION_RESIZE);
            i.putExtra("delta", delta);
            startService(i);
        }

        @JavascriptInterface
        public void setPetArt(boolean hd) {
            getSharedPreferences("ying_overlay", MODE_PRIVATE).edit().putBoolean("hd_art", hd).apply();
            refreshOverlayAppearance();
        }

        @JavascriptInterface
        public void refreshOverlayAppearance() {
            if (!OverlayService.isRunning()) return;
            Intent i = new Intent(MainActivity.this, OverlayService.class);
            i.setAction(OverlayService.ACTION_REFRESH_APPEARANCE);
            startService(i);
        }
    }

    private void toggleOverlay() {
        if (OverlayService.isRunning()) {
            stopService(new Intent(this, OverlayService.class));
            if (overlayButton != null) overlayButton.setText("开启桌面精灵");
            return;
        }
        if (!Settings.canDrawOverlays(this)) {
            waitingOverlayPermission = true;
            Intent i = new Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName())
            );
            startActivity(i);
            return;
        }
        startOverlay();
    }

    private void startOverlay() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 23);
        }
        Intent i = new Intent(this, OverlayService.class);
        i.setAction(OverlayService.ACTION_START);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i);
        else startService(i);
        if (overlayButton != null) overlayButton.setText("收起桌面精灵");
    }
    @Override
    protected void onPause() {
        super.onPause();
        if (OverlayService.isRunning()) {
            Intent intent = new Intent(this, OverlayService.class);
            intent.setAction(OverlayService.ACTION_SHOW_ON_DESKTOP);
            startService(intent);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (OverlayService.isRunning()) {
            Intent intent = new Intent(this, OverlayService.class);
            intent.setAction(OverlayService.ACTION_HIDE_IN_APP);
            startService(intent);
        }
        if (waitingOverlayPermission && Settings.canDrawOverlays(this)) {
            waitingOverlayPermission = false;
            startOverlay();
        }
        if (overlayButton != null) {
            overlayButton.setText(OverlayService.isRunning() ? "收起桌面精灵" : "开启桌面精灵");
        }
    }

    private String json(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }

    private int request(String method, String path, String body, boolean captureCookies) {
        for (String base : NetConfig.ordered(this)) {
            HttpURLConnection c = null;
            try {
                URL u = new URL(base + path);
                c = (HttpURLConnection)u.openConnection();
                c.setRequestMethod(method);
                c.setConnectTimeout(7000);
                c.setReadTimeout(25000);
                c.setUseCaches(false);
                c.setRequestProperty("Accept", "application/json");

                String cookies = CookieManager.getInstance().getCookie(base);
                if (cookies != null && !cookies.isEmpty()) {
                    c.setRequestProperty("Cookie", cookies);
                }
                if (body != null) {
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    byte[] data = body.getBytes(StandardCharsets.UTF_8);
                    c.setFixedLengthStreamingMode(data.length);
                    OutputStream out = c.getOutputStream();
                    out.write(data);
                    out.close();
                }

                int code = c.getResponseCode();

                if (captureCookies) {
                    for (Map.Entry<String, List<String>> e : c.getHeaderFields().entrySet()) {
                        if (e.getKey() != null && "Set-Cookie".equalsIgnoreCase(e.getKey())) {
                            for (String cookie : e.getValue()) {
                                NetConfig.mirrorCookie(cookie);
                            }
                        }
                    }
                }

                InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                if (in != null) {
                    byte[] buffer = new byte[1024];
                    while (in.read(buffer) != -1) { }
                    in.close();
                }

                if (code == 401 && "/api/mobile/whoami".equals(path)) {
                    continue;
                }

                NetConfig.saveBase(this, base);
                return code;
            } catch (Exception ignored) {
                // Try the next HTTPS endpoint.
            } finally {
                if (c != null) c.disconnect();
            }
        }
        return -1;
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            moveTaskToBack(true);
        }
    }
}
