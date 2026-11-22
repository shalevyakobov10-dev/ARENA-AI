# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 09-20→10-15 | 10-15→10-28 | z_entry=1.2, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.08 | +80.05 (19) | **+24.15** | +0.23 | 13 | 54% |
| 2 | 09-20→10-28 | 10-28→11-09 | z_entry=1.8, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.08 | +113.31 (29) | **+19.24** | +5.12 | 20 | 50% |
| 3 | 09-20→11-09 | 11-09→11-22 | z_entry=1.2, lookback_candles=12, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.04, stop_loss=0.08 | +139.51 (74) | **+240.61** | -13.02 | 40 | 57% |

**סה"כ מחוץ למדגם: +284.00 USDC על 73 עסקאות** (ללא השוק המוביל: **+16.94**, 12/20 שווקים חיוביים).
**עקביות: 100% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.