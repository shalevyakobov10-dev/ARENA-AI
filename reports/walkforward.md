# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-21→11-03 | 11-03→11-10 | z_entry=1.7, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +98.79 (15) | **+48.51** | +34.23 | 13 | 69% |
| 2 | 10-21→11-10 | 11-10→11-16 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +181.98 (29) | **+2.30** | -20.06 | 18 | 50% |
| 3 | 10-21→11-16 | 11-16→11-23 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.06, stop_loss=0.07 | +216.09 (46) | **+24.35** | +2.99 | 27 | 52% |

**סה"כ מחוץ למדגם: +75.16 USDC על 58 עסקאות** (ללא השוק המוביל: **+52.80**, 11/20 שווקים חיוביים).
**עקביות: 100% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.