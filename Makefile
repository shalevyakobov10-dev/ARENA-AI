.PHONY: reconcile backup readiness help install test doctor scan analyze calibrate sectors collect imbalance walkforward paper live backtest tune daily report research status serve sync deploy fees clean

help:
	@echo "make install   — התקנת תלויות (editable)"
	@echo "make test      — הרצת הטסטים"
	@echo "make doctor    — בדיקת חיבור וקונפיג"
	@echo "make scan      — סריקה חד-פעמית של סיגנלים"
	@echo "make analyze   — אבחון כוח ניבוי הסיגנל"
	@echo "make walkforward — כיול + מבחן OOS"
	@echo "make research  — שחזור ניסויי המחקר"
	@echo "make paper     — סימולציה (50 מחזורים)"
	@echo "make live      — מסחר אמיתי (מוגן ב-.env)"
	@echo "make backtest  — בקטסט על 6 שווקים מובילים"
	@echo "make tune      — סריקת פרמטרים"
	@echo "make calibrate — האם הצפי תואם את המציאות"
	@echo "make sectors   — איפה האות עובד (לפי סקטור)"
	@echo "make collect   — איסוף snapshots לחקר imbalance"
	@echo "make daily     — דוח יומי מה-DB"
	@echo "make report    — סיכום ביצועים מה-DB"
	@echo "make fees      — כלכלת העמלות לפי סקטור"
	@echo "make status    — מצב הבוט (בריאות/הון/פוזיציות)"
	@echo "make serve     — דשבורד לטלפון על :8787"
	@echo "make sync      — סנכרון בטוח מול GitHub"

install:
	pip install -e ".[dev]"

test:
	python -m pytest -q

doctor:
	pmmb doctor

scan:
	pmmb scan

reconcile:  ## סנכרון DB מול החשבון/בורסה
	pmmb reconcile

backup:  ## גיבוי חם של מסד הנתונים
	pmmb backup

readiness:  ## שער המעבר ל-live
	pmmb readiness

status:  ## מצב הבוט (בריאות, הון, פוזיציות)
	pmmb status

serve:  ## דשבורד לטלפון על :8787
	pmmb serve

sync:  ## סנכרון בטוח מול GitHub (עוצר אם בדיקות אדומות)
	./scripts/sync.sh "עדכון שוטף"

paper:
	pmmb paper --cycles 50 --interval 60

live:
	pmmb live --interval 60

analyze:
	pmmb analyze --markets 12 --lookback 1440

walkforward:
	pmmb walkforward --markets 10 --folds 3 --lookback 1440

research:
	python scripts/research_signal.py --markets 12

backtest:
	pmmb backtest --top 40 --lookback 1440

tune:
	pmmb tune --markets 4 --lookback 500

calibrate:
	pmmb calibrate --markets 16 --lookback 1440 --horizon 48

fees:  ## כלכלת העמלות לפי סקטור
	pmmb fees

sectors:
	pmmb sectors --markets 40 --horizon 48

collect:
	pmmb collect --minutes 30 --interval 20

imbalance:
	pmmb imbalance --horizon-min 60

daily:
	pmmb daily

report:
	pmmb report

clean:
	rm -rf pmmb.db logs reports/*.csv reports/*.json .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
