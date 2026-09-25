package com.yingbao.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.os.SystemClock;
import android.widget.ImageView;

/** Lightweight articulated render for the floating character. */
public class AnimatedCharacterView extends ImageView {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
    private final Rect source = new Rect();
    private final RectF target = new RectF();
    private Bitmap artwork, wave;
    private int poseResource;
    private long waveStart, nextIdle = SystemClock.uptimeMillis() + 16000;
    private float wind, windTarget;
    private long nextWind = 0;

    public AnimatedCharacterView(Context context) {
        super(context);
        setLayerType(LAYER_TYPE_SOFTWARE, null);
    }

    private Bitmap decode(int resource) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inScaled = false;
        options.inSampleSize = 2;
        return BitmapFactory.decodeResource(getResources(), resource, options);
    }

    @Override public void setImageResource(int resource) {
        poseResource = resource;
        artwork = decode(resource);
        invalidate();
    }

    @Override public void setImageBitmap(Bitmap bitmap) {
        artwork = bitmap;
        poseResource = 0;
        invalidate();
    }

    public void gesture() {
        if (poseResource != R.drawable.yingbao_pose_stand_light) return;
        if (wave == null) wave = decode(R.drawable.yingbao_pose_wave_light);
        waveStart = SystemClock.uptimeMillis();
        nextIdle = waveStart + 18000;
        invalidate();
    }

    private void render(Canvas canvas, Bitmap image, float alpha, double seconds,
                        float left, float top, float width, float height) {
        if (image == null || image.isRecycled()) return;
        int sourceWidth = image.getWidth(), sourceHeight = image.getHeight();
        float breathing = 1f + .008f * (float)Math.sin(seconds * 2.1);
        paint.setAlpha((int)(255f * Math.max(0f, Math.min(1f, alpha))));
        for (int sy = 0; sy < sourceHeight; sy += 24) {
            int bottom = Math.min(sourceHeight, sy + 24);
            float f = (sy + bottom) * .5f / sourceHeight;
            float hair = f < .62f ? (float)Math.sin(Math.PI * Math.min(1, f / .62f))
                * (wind + .75f * (float)Math.sin(seconds * 1.8 + f * 7)) : 0f;
            float skirt = f > .55f ? (wind * .8f
                + 1.1f * (float)Math.sin(seconds * 1.3 + f * 7)) * (f - .55f) / .45f : 0f;
            float tilt = f < .27f ? 1.4f * (float)Math.sin(seconds * .8) : 0f;
            float sliceWidth = f > .23f && f < .65f ? width * breathing : width;
            float x = left + (width - sliceWidth) * .5f + hair + skirt + tilt;
            float y = top + height * sy / sourceHeight;
            source.set(0, sy, sourceWidth, bottom);
            target.set(x, y, x + sliceWidth, y + height * (bottom - sy) / sourceHeight + .3f);
            canvas.drawBitmap(image, source, target, paint);
        }
        paint.setAlpha(255);
    }

    @Override protected void onDraw(Canvas canvas) {
        if (artwork == null) return;
        long now = SystemClock.uptimeMillis();
        double t = now / 1000.0;
        if (now >= nextWind) {
            windTarget = (float)(Math.random() * 2.6 - 1.3);
            nextWind = now + 1600 + (long)(Math.random() * 2100);
        }
        wind += (windTarget - wind) * .055f;
        float w = getWidth(), h = getHeight();
        float width = Math.min(w, h * 2f / 3f), height = width * 1.5f;
        float left = (w - width) / 2f, top = (h - height) / 2f;
        render(canvas, artwork, 1f, t, left, top, width, height);
        long elapsed = now - waveStart;
        if (wave != null && elapsed >= 0 && elapsed < 1650) {
            float fade = Math.min(1f, elapsed / 230f);
            fade = Math.min(fade, Math.min(1f, (1650 - elapsed) / 440f));
            render(canvas, wave, fade, t, left, top, width, height);
        }
        if (isShown()) postInvalidateDelayed(45);
    }
}
