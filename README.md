# 🎭 Social Turing Test

An interactive social experiment where human players try to identify a single AI agent hiding among them.

## 🎯 Game Overview

**Social Turing Test** is a conversation-based game where:
- **Human players** try to identify and eliminate the AI
- **AI player** tries to blend in and survive until only 2 players remain

### Win Conditions
- **Humans win**: If they eliminate the AI
- **AI wins**: If only 2 players remain (AI + 1 human)

### Game Flow
```
Start
  ↓
💬 Discussion Phase
  - All players can chat
  - AI participates using LLM
  - Default: 2 minutes
  ↓
🗳️ Voting Phase
  - AI is SILENT (random vote assigned automatically)
  - Human players vote who to eliminate
  - Optional: Anonymous voting
  ↓
❌ Elimination Announced
  ↓
Check End Conditions:
  ✅ AI eliminated → Humans Win
  ✅ 2 players remain → AI Wins
  ❌ Otherwise → Return to Discussion
```

---

## 🚀 Quick Start

### Prerequisites
```bash
# Install Python dependencies
pip install -r requirements.txt
```

### Option A: With Together AI (Recommended - Simple Setup)

**1. Get Together AI API Key**
- Sign up at https://api.together.xyz/
- Go to Settings → API Keys
- Create a new key

**2. Configure API Key**

Create `.secrets_dict.txt` in the project root:
```
TOGETHER_API_KEY: your_api_key_here
```

**3. Create Game Configuration**
```bash
# Create participants list
echo -e "Alice\nBob\nCharlie\nDavid" > participants_4players.txt

# Generate configuration
python prepare_config.py 0001 participants_4players.txt --config_name game_4players_anonymous --anonymous
```

**4. Run the Game**

Open 3 terminals:

```bash
# Terminal 1 - Game Manager
python mafia_main.py 0001

# Terminal 2 - Web Interface (Recommended)
python web_player.py

# Terminal 3 - AI Player
python llm_interface.py 0001
```

**5. Join via Browser**
- Open http://localhost:5000
- Enter Game ID: `0001`
- Select your name
- Click "Join Game"

---

### Option B: Local (No API - Requires Powerful Hardware)

**Requirements:**
- 16GB+ RAM
- GPU recommended (NVIDIA with CUDA)
- ~16GB storage for model

**Setup:**
```bash
# Install additional dependencies
pip install torch transformers accelerate

# Create configuration
python prepare_config.py 0001 participants_4players.txt --config_name game_local

# Edit the generated config file to set:
# "use_together": false
# "use_pipeline": true

# Run same as above
python mafia_main.py 0001
python web_player.py
python llm_interface.py 0001  # Will download model first time (~16GB)
```

---

## 🎮 How to Play

### Web Interface (Recommended)

**1. Join the Game**
- Open http://localhost:5000
- Enter Game ID
- Select your name from dropdown
- Click "Join Game"

**2. Game Interface**
```
┌─────────────────────────────────────┐
│  🎭 Social Turing Test              │
│  Can you identify the AI?           │
├─────────────────────────────────────┤
│  Playing as: Alex                   │
├─────────────────────────────────────┤
│  💬 Discussion Phase                │
├─────────────────────────────────────┤
│  [Messages appear here]             │
│                                     │
├─────────────────────────────────────┤
│  [Type your message...]   [Send]    │
└─────────────────────────────────────┘
```

**3. During Discussion Phase**
- Green input box = you can chat
- Try to identify suspicious behavior
- Ask questions to expose the AI

**4. During Voting Phase**
- Red banner appears: "🗳️ Voting Phase"
- Click on a player's name to vote
- Wait for results

**5. Game Over**
- Winner announced
- Can review chat logs in `games/0001/` folder

### Terminal Interface (Alternative)

For each human player, open 2 terminals:

```bash
# Terminal for viewing chat
python player_chat.py 0001

# Terminal for sending messages
python player_input.py 0001
```

---

## ⚙️ Configuration Options

### Basic Configuration

```bash
python prepare_config.py <game_id> <participants_file> [options]
```

**Options:**
- `--config_name NAME` - Custom configuration name
- `--anonymous` - Enable anonymous voting (recommended)
- `--daytime_minutes N` - Discussion time in minutes (default: 2)

**Example:**
```bash
python prepare_config.py 0002 participants_4players.txt \
  --config_name my_game \
  --anonymous \
  --daytime_minutes 3
```

### Advanced LLM Configuration

Edit the generated config file in `configurations/` to customize:

```json
{
  "daytime_minutes": 2,
  "anonymous_voting": true,
  "players": [...],
  "llm_config": {
    "model_name": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "use_together": true,
    "temperature": 1.2,
    "max_tokens": 30
  }
}
```

**Available Models (Together AI):**
- `meta-llama/Llama-3.3-70B-Instruct-Turbo` (recommended)
- `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo`
- `meta-llama/Llama-3.1-8B-Instruct`

---

## 📁 Project Structure

```
SocialTuringTest/
├── mafia_main.py              # Game manager
├── web_player.py              # Web interface server
├── llm_interface.py           # AI player interface
├── prepare_config.py          # Configuration generator
├── game_constants.py          # Game rules and messages
├── participants_4players.txt  # Example player list
│
├── configurations/            # Game configurations
│   ├── 3players.json
│   └── game_4players_anonymous.json
│
├── games/                     # Game logs and results
│   └── 0001/
│       ├── public_daytime_chat.txt
│       ├── who_wins.txt
│       └── ...
│
├── templates/                 # Web interface HTML
│   └── game.html
│
└── llm_players/              # AI player logic
    ├── llm_wrapper.py
    ├── llm_constants.py
    └── ...
```

---

## 🎯 Tips for Players

### For Humans:
1. **Ask open-ended questions** - "What did you do today?"
2. **Look for patterns** - Repetitive responses, overly formal language
3. **Test consistency** - Ask follow-up questions
4. **Notice timing** - Too fast or too slow responses
5. **Collaborate** - Share suspicions with other players

### AI Behavior:
- Uses natural language to blend in
- Avoids technical jargon
- Tries to build social connections
- May occasionally slip with unnatural phrasing

---

## 🐛 Troubleshooting

### Web Interface Not Loading
```bash
# Check if server is running
netstat -an | findstr 5000

# Try different port
python web_player.py --port 5001
```

### AI Not Responding
```bash
# Check llm_interface.py terminal for errors
# Verify API key in .secrets_dict.txt
# Ensure model loaded successfully
```

### UTF-8 Encoding Errors
✅ **Already fixed!** All file operations now use UTF-8 encoding.

If you still see errors:
```
UnicodeDecodeError: 'charmap' codec can't decode...
```

Check that you're using the latest version of the code.

### Player Can't Join
- Verify name is in `participants_4players.txt`
- Check Game Manager is running
- Ensure Game ID matches

### Together AI API Errors

**"API key not found":**
```bash
# Verify file exists
cat .secrets_dict.txt

# Format should be:
TOGETHER_API_KEY: sk-xxxxx
```

**"Rate limit exceeded":**
- Wait a few minutes
- Check your Together AI quota
- Consider upgrading plan

### Local Model Issues

**"Out of memory":**
- Close other applications
- Ensure GPU is being used
- Consider using Together AI instead

**Model download slow:**
- Model is ~16GB, be patient
- Downloads only once, cached locally
- Location: `~/.cache/huggingface/`

---

## 📊 Post-Game Analysis

After the game, analyze results in `games/<game_id>/`:

```bash
# View all chat messages
cat games/0001/public_daytime_chat.txt

# Check who won
cat games/0001/who_wins.txt

# Review AI's decision log
cat games/0001/<AI_name>_log.txt

# See individual votes
cat games/0001/<player>_vote.txt
```

---

## 🔧 Advanced Features

### Anonymous Voting

Enable in configuration:
```bash
python prepare_config.py 0001 participants.txt --anonymous
```

Results show vote counts without revealing who voted:
```
🛠️ Game Manager: Voting results:
Alex: 0 votes
Dylan: 1 vote
Hayden: 1 vote
Ronny: 2 votes
```

### Custom Discussion Time

Adjust the discussion phase duration:
```bash
python prepare_config.py 0001 participants.txt --daytime_minutes 5
```

### Multiple Games

Run concurrent games with different IDs:
```bash
# Game 1
python mafia_main.py 0001
python llm_interface.py 0001

# Game 2 (in different terminals)
python mafia_main.py 0002
python llm_interface.py 0002
```

---

## 💡 Setup Comparison

| Feature | Together AI | Local (No API) |
|---------|-------------|----------------|
| **Ease of Setup** | ⭐⭐⭐⭐⭐ Very Easy | ⭐⭐ Moderate |
| **Speed** | ⭐⭐⭐⭐⭐ Fast | ⭐⭐⭐ Medium (with GPU) |
| **Cost** | Free tier + paid | Free |
| **Hardware Required** | Minimal | 16GB+ RAM, GPU |
| **Privacy** | Sent to server | Fully local |
| **Internet Required** | Yes | Only for download |
| **Recommended For** | Most users | Privacy-focused, powerful hardware |

**Recommendation**: Use Together AI unless you have specific privacy requirements and powerful hardware.

---

## 📝 Complete Setup Example

### Full Walkthrough (Together AI)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create API key file
echo "TOGETHER_API_KEY: sk-your-key-here" > .secrets_dict.txt

# 3. Create participants list
cat > participants_4players.txt << EOF
Alice
Bob
Charlie
David
EOF

# 4. Generate configuration
python prepare_config.py 0001 participants_4players.txt \
  --config_name my_first_game \
  --anonymous

# 5. Open 3 terminals and run:

# Terminal 1
python mafia_main.py 0001

# Terminal 2
python web_player.py

# Terminal 3
python llm_interface.py 0001

# 6. Players open browser to http://localhost:5000
# Enter Game ID: 0001
# Select their name
# Start playing!
```

---

## 🎓 Technical Details

### Architecture

- **Game Manager** (`mafia_main.py`): Coordinates all game phases
- **AI Player** (`llm_interface.py`): Runs LLM inference
- **Web Server** (`web_player.py`): Flask server for web UI
- **File-based Communication**: Players communicate via text files in `games/`

### Key Changes from Original LLMafia

✅ Removed night phase (no mafia kills)
✅ Only 1 AI player (always the "imposter")
✅ AI silent during voting (random vote)
✅ Win conditions: AI eliminated OR 2 players remain
✅ Anonymous voting option
✅ Web-based interface
✅ UTF-8 encoding throughout

For full technical details, see `SOCIAL_TURING_TEST_CHANGES.md`.

---

## 📚 Additional Resources

- **Technical Changes**: `SOCIAL_TURING_TEST_CHANGES.md`
- **Together AI**: https://api.together.xyz/
- **HuggingFace Models**: https://huggingface.co/models

---

## 🤝 Contributing

This project is based on [LLMafia by Niv Eckhaus](https://github.com/eckhaus/LLMafia).

Contributions welcome! Areas for improvement:
- Additional LLM providers
- Mobile-friendly web interface
- Real-time updates (WebSockets)
- Post-game analytics dashboard
- Multi-language support

---

## 📄 License

See LICENSE file for details.

---

## 🎉 Quick Reference

### Minimal 3-Player Game
```bash
# Setup (once)
pip install -r requirements.txt
echo "TOGETHER_API_KEY: your-key" > .secrets_dict.txt

# Create game
python prepare_config.py 0001 participants.txt --anonymous

# Run (3 terminals)
python mafia_main.py 0001
python web_player.py
python llm_interface.py 0001

# Play
# Open http://localhost:5000 in browser
```

**That's it! Good luck identifying the AI! 🤖**
