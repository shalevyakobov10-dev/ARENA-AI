# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-21→11-03 | 11-03→11-10 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.07 | +81.99 (14) | **+45.64** | +28.41 | 14 | 57% |
| 2 | 10-21→11-10 | 11-10→11-16 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.07 | +142.87 (29) | **+9.76** | -9.51 | 23 | 52% |
| 3 | 10-21→11-16 | 11-16→11-23 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +181.43 (52) | **+0.79** | -11.18 | 17 | 59% |

**סה"כ מחוץ למדגם: +56.19 USDC על 54 עסקאות** (ללא השוק המוביל: **+28.23**, 13/21 שווקים חיוביים).
**עקביות: 100% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.