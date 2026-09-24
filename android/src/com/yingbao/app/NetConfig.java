package com.yingbao.app;

import android.content.Context;
import android.webkit.CookieManager;

import java.util.ArrayList;
import java.util.List;

public final class NetConfig {
    public static final String[] BASES = new String[] {
        "https://38-76-190-23.nip.io",
        "https://38-76-190-23.sslip.io",
        "https://38.76.190.23"
    };

    private static final String PREFS = "yingbao_net";
    private static final String KEY_BASE = "active_base";

    private NetConfig() {}

    public static String getBase(Context c) {
        String saved = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_BASE, BASES[0]);
        for (String b : BASES) if (b.equals(saved)) return saved;
        return BASES[0];
    }

    public static void saveBase(Context c, String base) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_BASE, base).apply();
    }

    public static String[] ordered(Context c) {
        String active = getBase(c);
        List<String> out = new ArrayList<>();
        out.add(active);
        for (String b : BASES) if (!b.equals(active)) out.add(b);
        return out.toArray(new String[0]);
    }

    public static void mirrorCookie(String cookie) {
        if (cookie == null || cookie.isEmpty()) return;
        CookieManager cm = CookieManager.getInstance();
        for (String b : BASES) cm.setCookie(b, cookie);
        cm.flush();
    }

    public static void syncExistingCookies() {
        CookieManager cm = CookieManager.getInstance();
        for (String source : BASES) {
            String cookie = cm.getCookie(source);
            if (cookie != null && !cookie.isEmpty()) {
                mirrorCookie(cookie);
                return;
            }
        }
    }
}
