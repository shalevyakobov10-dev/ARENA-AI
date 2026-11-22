# Walk-Forward — מנוע `meanrev` (stop_mode=abs)

| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |
|---|---|---|---|---|---|---|---|---|
| 1 | 10-20→11-02 | 11-02→11-09 | z_entry=1.7, rsi_max=45.0, lookback_candles=12, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.07 | +21.24 (12) | **+17.72** | +13.49 | 15 | 73% |
| 2 | 10-20→11-09 | 11-09→11-16 | z_entry=1.8, rsi_max=45.0, lookback_candles=12, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.08 | +44.16 (25) | **-3.97** | -7.44 | 18 | 56% |
| 3 | 10-20→11-16 | 11-16→11-22 | z_entry=1.8, rsi_max=40.0, lookback_candles=24, reversion_ratio=0.55, min_score=0.55, trend_guard=False, take_profit=0.05, stop_loss=0.07 | +61.06 (37) | **+14.11** | +5.03 | 23 | 52% |

**סה"כ מחוץ למדגם: +27.85 USDC על 56 עסקאות** (ללא השוק המוביל: **+20.76**, 13/16 שווקים חיוביים).
**עקביות: 67% מהחלונות היו חיוביים.**

> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא
> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.