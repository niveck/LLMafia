# מדריך הרצה מקומית ללא API (HuggingFace Pipeline)

## התקנה ראשונית

### 1. דרישות חומרה:
- **RAM**: לפחות 16GB
- **GPU**: אופציונלי אבל מומלץ מאוד (NVIDIA עם CUDA)
- **Storage**: ~16GB למודל

### 2. התקן חבילות Python:
```bash
pip install -r requirements.txt
pip install torch transformers accelerate
```

### 3. (אופציונלי) התקן תמיכת GPU:
אם יש לך NVIDIA GPU:
```bash
# לינוקס/Windows
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# macOS (MPS support)
# pip כבר מתקין את הגרסה הנכונה
```

## יצירת משחק עם LLM מקומי

### שלב 1: צור רשימת משתתפים
צור קובץ `participants.txt`:
```
Alice
Bob
Charlie
David
```

### שלב 2: צור קונפיגורציה
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 2
```

**בזמן יצירת הקונפיג:**
- כשתשאל "change LLM config?", תוכל ללחוץ Enter (להשאיר ברירת מחדל)
- או להזין `-c` בפקודה כדי לשנות הגדרות

### שלב 3: ערוך את הקונפיג להרצה מקומית

פתח את קובץ הקונפיג שנוצר (למשל `configurations/config<תאריך>.json`) וערוך:

```json
"llm_config": {
    "model_name": "meta-llama/Llama-3.1-8B-Instruct",
    "use_together": false,
    "use_pipeline": true,
    ...
}
```

שנה את:
- `"use_together": true` ל-`false`
- `"use_pipeline": false` ל-`true`

**המודל שיורץ**: Llama-3.1-8B-Instruct (ברירת המחדל בקוד המקורי)

### שלב 4: הכן את המשחק
```bash
python prepare_game.py 0034
```
(החלף `0034` במספר המשחק שקיבלת)

## הרצת המשחק

### הורדת המודל (פעם אחת):
בפעם הראשונה, HuggingFace יוריד את Llama-3.1-8B (~16GB).
זה יכול לקחת 10-30 דקות תלוי במהירות האינטרנט.

### הרץ:

**Terminal 1 - מנהל:**
```bash
python mafia_main.py 0034
```

**Terminal 2 - AI (מקומי):**
```bash
python llm_interface.py 0034
```

**הודעה שתראה:**
```
Loading model: meta-llama/Llama-3.1-8B-Instruct
Downloading (if first time)...
Model loaded successfully!
The LLM Player was loaded successfully...
```

**Terminals 3+ - שחקנים:**
```bash
# כל שחקן
python player_chat.py 0034    # צפייה
python player_input.py 0034   # קלט
```

## דרישות מערכת

### Llama-3.1-8B-Instruct:
- **גודל**: ~16GB
- **RAM נדרש**: 16GB מינימום (32GB מומלץ)
- **GPU**: מומלץ מאוד (8GB+ VRAM)
- **מהירות**: בינונית עד מהירה (עם GPU)
- **איכות**: מעולה

### שימוש ב-GPU:
הקוד יזהה GPU אוטומטית. לבדיקה:
```python
import torch
print(torch.cuda.is_available())  # True אם יש GPU
```

## Cache ואחסון

### המודל נשמר ב:
- **Linux/Mac**: `~/.cache/huggingface/hub/`
- **Windows**: `C:\Users\<username>\.cache\huggingface\hub\`

### לנקות cache (אם נגמר מקום):
```bash
rm -rf ~/.cache/huggingface/hub/
```

## פתרון בעיות

### שגיאה: "Out of memory"
1. סגור כל התוכניות האחרות
2. השתמש ב-GPU אם אפשר
3. הוסף RAM פיזי למחשב

### שגיאה: "Model not found"
```bash
# התחבר ל-HuggingFace (אם המודל דורש הרשאה)
huggingface-cli login
```

### AI איטי מדי
1. וודא שיש GPU והוא בשימוש
2. סגור תוכניות רקע
3. בדוק שהמודל נטען ל-GPU (לא CPU)

### המודל לא מוריד
```bash
# הורד ידנית
from transformers import pipeline
pipe = pipeline("text-generation", model="meta-llama/Llama-3.1-8B-Instruct")
```

## השוואה: Local vs Together AI

| תכונה | Local (Llama-3.1-8B) | Together AI |
|--------|----------------------|-------------|
| מהירות | בינונית-מהירה (GPU) | מהירה |
| עלות | חינם | Free tier + תשלום |
| דרישות חומרה | 16GB+ RAM, GPU מומלץ | אין |
| הגדרה | צריך לערוך config | פשוטה |
| פרטיות | מלאה | נשלח לשרת |
| זמינות | תמיד | תלוי באינטרנט |

## דוגמה מלאה

```bash
# 1. צור רשימת משתתפים
cat > participants.txt << EOF
Alice
Bob
Charlie
David
EOF

# 2. צור קונפיגורציה
python prepare_config.py -p 5 -l 1 -n participants.txt -dt 2

# נניח קיבלת: configurations/config291124_2359.json

# 3. ערוך את הקונפיג:
# פתח את הקובץ ושנה:
# "use_together": false
# "use_pipeline": true

# 4. הכן משחק (נניח קיבלת 0035)
python prepare_game.py 0035

# 5. הרץ (בטרמינלים נפרדים)
python mafia_main.py 0035       # T1 - מנהל
python llm_interface.py 0035    # T2 - AI (ייקח זמן בפעם הראשונה!)
python player_chat.py 0035      # T3 - שחקן 1
python player_input.py 0035     # T4 - שחקן 1
python player_chat.py 0035      # T5 - שחקן 2
python player_input.py 0035     # T6 - שחקן 2
# ... וכן הלאה
```

## טיפים חשובים

1. **פעם ראשונה**: ההורדה לוקחת זמן - תכנן מראש
2. **GPU חובה**: ללא GPU המשחק יהיה איטי מאוד
3. **RAM**: סגור כל דפדפן/תוכנה אחרת לפני המשחק
4. **סבלנות**: טעינת המודל לוקחת 1-2 דקות בפעם הראשונה

---

**סיכום**: הרצה מקומית מתאימה אם:
✅ יש לך חומרה חזקה (16GB+ RAM, GPU)
✅ רוצה פרטיות מלאה
✅ לא רוצה להסתמך על אינטרנט/API
✅ מוכן לערוך קובץ config ידנית

**אחרת**: Together AI הרבה יותר פשוט! (ראה `SETUP_WITH_TOGETHER_AI.md`)
