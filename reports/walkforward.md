# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-21→11-03 | 11-03→11-09 | z_entry=1.2, lookback_candles=12, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.1 | +24.89 (10) | **+13.27** | +5.56 | 5 | 60% |
| 2 | 10-21→11-09 | 11-09→11-16 | z_entry=1.2, lookback_candles=12, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.1 | +36.56 (15) | **-18.37** | -19.98 | 5 | 20% |
| 3 | 10-21→11-16 | 11-16→11-22 | z_entry=1.8, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.04, stop_loss=0.08 | +23.68 (14) | **-1.46** | -4.92 | 3 | 33% |

**סה"כ מחוץ למדגם: -6.56 USDC על 13 עסקאות** (ללא השוק המוביל: **-14.12**, 3/7 שווקים חיוביים).
**עקביות: 33% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.