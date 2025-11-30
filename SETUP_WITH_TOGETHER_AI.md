# מדריך הרצה עם Together AI API

## התקנה ראשונית

### 1. התקן חבילות Python:
```bash
pip install -r requirements.txt
```

### 2. השג API Key מ-Together AI:
1. הרשם ב-https://api.together.xyz/
2. עבור ל-Settings → API Keys
3. צור API key חדש
4. העתק את ה-key

### 3. הגדר את ה-API Key:
צור קובץ בשם `.secrets_dict.txt` בתיקיית הפרויקט:
```
TOGETHER_API_KEY: your_api_key_here
```

**חשוב**: החלף `your_api_key_here` ב-API key האמיתי שלך!

## יצירת משחק

### שלב 1: צור רשימת משתתפים
צור קובץ `participants.txt`:
```
Alice
Bob
Charlie
David
```

### שלב 2: צור קונפיגורציה עם Together AI
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 2
```

**פרמטרים:**
- `-p 5` = סה"כ 5 שחקנים (1 AI + 4 בני אדם)
- `-l 1` = 1 שחקן AI
- `-n participants.txt` = רשימת משתתפים
- `-dt 2` = 2 דקות לכל שלב דיון

הקונפיגורציה תשתמש אוטומטית ב-Together AI (זו ברירת המחדל).

**המודל המוגדר כברירת מחדל:**
- `meta-llama/Llama-3.3-70B-Instruct-Turbo-Free`

### (אופציונלי) שנה הגדרות LLM:
אם רוצה לשנות מודל או פרמטרים:
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -c
```

הדגל `-c` יאפשר לך לבחור:
- מודל אחר (Llama 3.1, Phi-3, וכו')
- Temperature
- Max tokens
- פרמטרים נוספים

### שלב 3: הכן את המשחק
```bash
python prepare_game.py 0034
```
(החלף `0034` במספר המשחק שקיבלת)

## הרצת המשחק

### סדר הפעלה:

**Terminal 1 - מנהל המשחק:**
```bash
python mafia_main.py 0034
```

**Terminal 2 - שחקן AI (עם Together):**
```bash
python llm_interface.py 0034
```
ה-AI יתחבר ל-Together API ויתחיל לפעול.

**Terminals 3+ - שחקנים אנושיים:**

לכל שחקן צריך 2 טרמינלים:

**Alice:**
```bash
# Terminal 3 - צפייה
python player_chat.py 0034

# Terminal 4 - קלט
python player_input.py 0034
```

**Bob:**
```bash
# Terminal 5 - צפייה
python player_chat.py 0034

# Terminal 6 - קלט
python player_input.py 0034
```

וכן הלאה לכל שחקן.

## בדיקת תקינות

### בדוק שה-API Key עובד:
אחרי הפעלת `llm_interface.py`, אמור לראות:
```
The LLM Player was loaded successfully, now waiting for all other players to join...
```

אם יש שגיאת API, בדוק:
1. שהקובץ `.secrets_dict.txt` קיים
2. שה-API key נכון
3. שיש לך קרדיט ב-Together AI

## עלויות

Together AI מציע:
- **Free tier** עם מכסה חודשית
- **Pay as you go** אחרי המכסה

משחק טיפוסי (5 שחקנים, 2 דקות לסיבוב):
- ~10-20 קריאות API
- ~500-1000 tokens סה"כ
- עלות נמוכה מאוד (כמה סנטים)

## מודלים זמינים ב-Together AI

1. **Llama-3.3-70B-Instruct-Turbo-Free** (מומלץ, ברירת מחדל)
   - חזק ומהיר
   - חינמי בתור "Turbo-Free"

2. **Llama-3.1-8B-Instruct**
   - קטן ומהיר יותר
   - טוב לבדיקות

3. **Phi-3-mini-4k-instruct**
   - מודל קטן של Microsoft
   - מאוד מהיר

## פתרון בעיות

### שגיאה: "API key not found"
```bash
# ודא שהקובץ קיים
ls -la .secrets_dict.txt

# בדוק את התוכן
cat .secrets_dict.txt
```

### שגיאה: "Rate limit exceeded"
- חכה כמה דקות
- או שדרג את התוכנית ב-Together AI

### שגיאה: "Model not found"
- ודא ששם המודל נכון בקובץ הקונפיגורציה
- בדוק ב-Together AI אילו מודלים זמינים

### ה-AI לא מגיב
1. בדוק בטרמינל של `llm_interface.py` אם יש שגיאות
2. ודא שהמשחק התחיל (כל השחקנים התחברו)
3. בדוק את קבצי הלוג ב-`games/0034/`

## דוגמה מלאה

```bash
# 1. צור רשימת משתתפים
echo -e "Alice\nBob\nCharlie\nDavid" > participants.txt

# 2. צור קונפיגורציה
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 2

# נניח קיבלת game_id: 0034

# 3. הכן משחק
python prepare_game.py 0034

# 4. הרץ (בטרמינלים נפרדים):
python mafia_main.py 0034           # Terminal 1
python llm_interface.py 0034        # Terminal 2
python player_chat.py 0034          # Terminal 3 (Alice view)
python player_input.py 0034         # Terminal 4 (Alice input)
python player_chat.py 0034          # Terminal 5 (Bob view)
python player_input.py 0034         # Terminal 6 (Bob input)
# ... וכן הלאה
```

## טיפים לביצועים

1. **מודל מהיר**: השתמש ב-Llama-3.3-70B-Turbo-Free
2. **Temperature נמוך**: 1.0-1.3 לתגובות יציבות
3. **Max tokens**: 20-30 מספיק להודעות קצרות
4. **זמן דיון**: 2-3 דקות אידיאלי

## לוגים ומעקב

אחרי המשחק, בדוק:
- `games/0034/<AI_name>_log.txt` - כל הפעולות של ה-AI
- `games/0034/all_messages.txt` - כל השיחה
- `games/0034/who_wins.txt` - תוצאות

---

**הערה**: Together AI הוא השירות המומלץ כי:
✅ קל להתקנה
✅ מהיר
✅ Free tier נדיב
✅ מודלים חזקים
