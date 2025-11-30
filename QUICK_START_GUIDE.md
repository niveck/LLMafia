# Quick Start Guide - Social Turing Test

## התקנה ראשונית

### 1. התקן חבילות Python נדרשות:
```bash
pip install -r requirements.txt
```

### 2. הגדר API Key (אם משתמש ב-Together AI):
צור קובץ בשם `.secrets_dict.txt` בתיקיית הפרויקט:
```
TOGETHER_API_KEY: your_api_key_here
```

## יצירת משחק חדש

### שלב 1: צור קובץ רשימת משתתפים
צור קובץ טקסט עם שמות השחקנים האנושיים (שורה אחת לשם):

**דוגמה** - `participants.txt`:
```
Alice
Bob
Charlie
David
```

### שלב 2: צור קונפיגורציה למשחק
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 3
```

**פרמטרים:**
- `-p 5` = סה"כ 5 שחקנים (1 AI + 4 בני אדם)
- `-l 1` = 1 שחקן AI (תמיד חייב להיות 1)
- `-n participants.txt` = קובץ עם שמות המשתתפים
- `-dt 3` = 3 דקות לכל שלב דיון (אופציונלי, ברירת מחדל: 2)

זה ייצור קובץ קונפיגורציה ב-`configurations/` עם מספר משחק.

### שלב 3: הכן את המשחק
```bash
python prepare_game.py <game_id>
```
החלף `<game_id>` במספר שקיבלת (למשל: `0034`).

זה יצור תיקייה ב-`games/0034/` עם כל הקבצים הנדרשים.

## הרצת המשחק

### Terminal 1 - הפעל את מנהל המשחק:
```bash
python mafia_main.py 0034
```

### Terminal 2 - הפעל את שחקן ה-AI:
```bash
python llm_interface.py 0034
```

### Terminals 3+ - כל שחקן אנושי מריץ שני סקריפטים:

**Terminal לצפייה (chat):**
```bash
python player_chat.py 0034
```

**Terminal להזנת קלט (input):**
```bash
python player_input.py 0034
```

## סדר ההרצה המומלץ

1. **ראשון**: הפעל `mafia_main.py` (מנהל המשחק)
2. **שני**: הפעל `llm_interface.py` (ה-AI)
3. **אחר כך**: כל שחקן אנושי מפעיל את שני הסקריפטים שלו
4. המשחק מתחיל אוטומטית כשכולם מחוברים

## מהלך המשחק

### שלב דיון:
- כל השחקנים (כולל ה-AI) יכולים לשלוח הודעות
- נסו לזהות מי ה-AI
- ה-AI ינסה להתחזות לאדם

### שלב הצבעה:
- כל שחקן מצביע למי לחסל
- **ה-AI שותק לגמרי** - ההצבעה שלו אקראית
- המערכת מכריזה מי חוסל

### תנאי ניצחון:
- **בני אדם מנצחים**: אם חיסלו את ה-AI
- **AI מנצח**: אם נשארו רק 2 שחקנים (AI + 1 אדם)

## דוגמת הרצה מלאה

```bash
# Terminal 1 - Game Manager
python mafia_main.py 0034

# Terminal 2 - AI Player  
python llm_interface.py 0034

# Terminal 3 - Alice (chat)
python player_chat.py 0034

# Terminal 4 - Alice (input)
python player_input.py 0034

# Terminal 5 - Bob (chat)
python player_chat.py 0034

# Terminal 6 - Bob (input)
python player_input.py 0034

# ... וכן הלאה לכל שחקן
```

## פקודות שימושיות

### צור משחק מהיר לבדיקה (ללא AI):
```bash
python prepare_config.py -p 3 -l 0 -dt 1
```

### צור משחק עם AI (מומלץ):
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 2
```

### ערוך את הגדרות ה-AI:
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -c
```
הדגל `-c` מאפשר לך לשנות פרמטרים של ה-LLM.

## בעיות נפוצות

### שגיאה: "No LLM player configured"
- וודא ש-`-l 1` מוגדר ביצירת הקונפיגורציה

### שגיאה: API Key
- בדוק שקובץ `.secrets_dict.txt` קיים ומכיל את ה-API key

### המשחק לא מתחיל
- וודא שכל השחקנים (כולל ה-AI) הצטרפו
- בדוק ב-Terminal של `mafia_main.py` אילו שחקנים עדיין חסרים

## קבצי לוג ותוצאות

אחרי המשחק, תמצא ב-`games/<game_id>/`:
- `all_messages.txt` - כל ההודעות
- `public_daytime_chat.txt` - צ'אט הדיון
- `who_wins.txt` - מי ניצח
- `<player>_log.txt` - לוגים של ה-AI
- `<player>_vote.txt` - הצבעות של כל שחקן

## טיפים למשחק טוב

1. **מינימום 4-5 שחקנים** מומלץ לחוויה טובה
2. **זמן דיון**: 2-3 דקות מספיק (לא יותר מדי)
3. **הסבר לשחקנים** את החוקים לפני שמתחילים
4. **נסו משחק ניסיון** קצר קודם עם 3 שחקנים

## עזרה נוספת

ראה את `SOCIAL_TURING_TEST_CHANGES.md` לפרטים טכניים על השינויים שנעשו.
