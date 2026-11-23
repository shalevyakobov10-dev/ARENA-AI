# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-21→11-03 | 11-03→11-10 | z_entry=1.7, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +30.02 (16) | **+30.82** | +21.87 | 19 | 68% |
| 2 | 10-21→11-10 | 11-10→11-16 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +67.36 (34) | **+13.53** | +0.88 | 19 | 53% |
| 3 | 10-21→11-16 | 11-16→11-23 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +86.73 (51) | **+16.20** | +8.00 | 27 | 48% |

**סה"כ מחוץ למדגם: +60.55 USDC על 65 עסקאות** (ללא השוק המוביל: **+46.84**, 14/21 שווקים חיוביים).
**עקביות: 100% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.