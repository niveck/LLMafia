# Social Turing Test Conversion - Complete Implementation Summary

This document summarizes all changes made to convert the LLMafia codebase into a Social Turing Test competitive game.

## Overview

The game has been transformed from a multi-player Mafia game into a Social Turing Test where:
- **ONE AI player** (the "Imposter") tries to blend in with human players
- **All other players are humans** trying to identify the AI
- **No night phase** - only discussion and voting rounds
- **Win conditions**: Humans win if they eliminate the AI; AI wins if only 2 players remain (AI + 1 human)

---

## Core Files Modified

### 1. `game_constants.py`
**Changes:**
- Added new role display names: `IMPOSTER_ROLE` = "Imposter", `HUMAN_ROLE` = "Human"
- Updated win messages: `AI_WINS_MESSAGE`, `HUMANS_WIN_MESSAGE`
- Rewrote `RULES_OF_THE_GAME` to explain Social Turing Test mechanics
- Updated all UI messages to use "Discussion Time" instead of "Daytime"
- Changed voting prompt to "Who do you think is the AI?"
- Updated elimination message to show "AI" instead of "Imposter"
- Added `get_role_display_string()` function for user-facing role names
- Removed "Your role" announcement for human players

### 2. `mafia_main.py`
**Major Changes:**
- **Removed night phase entirely**: Deleted `run_nighttime()` function and all references
- **New win conditions** in `is_game_over()`:
  - Humans win: `len(mafia_players) == 0` (AI eliminated)
  - AI wins: `len(players) == 2 and len(mafia_players) == 1`
- **Simplified game loop**: Only runs `run_daytime()` repeatedly until game ends
- **UTF-8 encoding fix**: All file read/write operations now use `encoding="utf-8", errors="ignore"`
  - Fixed 7+ locations including Player.get_new_messages(), get_config(), voting_sub_phase(), etc.
  - Prevents UnicodeDecodeError when reading files with emojis or special characters
- **Anonymous voting support**: Added `anonymous_voting` parameter throughout voting functions
- Updated `announce_voted_out_player()` to use display role names
- Updated `get_voted_out_name()` to show vote counts only in anonymous mode

### 3. `prepare_config.py`
**Changes:**
- **Force exactly 1 imposter**: Modified to always set exactly 1 AI player (the imposter)
- **Enhanced CLI arguments**:
  - Added `--config_name` for custom configuration names
  - Added `--anonymous` flag for anonymous voting
  - Added `--daytime_minutes` for custom discussion time
  - Uses positional args: `game_id` and `participants_file`
- **Auto-set nighttime to 0**: Ensures no night phase duration
- Minimum players changed to 3 (1 AI + 2 humans minimum)
- The single imposter is randomly selected and assigned to the AI
- Removed multi-mafia logic and validation

### 4. `llm_interface.py`
**Critical Changes:**
- **Random voting**: Completely rewrote `get_vote_from_llm()`:
  - AI vote is always random (no LLM decision)
  - AI cannot vote for itself
  - No messages or rationale shown during voting
  - Vote is logged as "MODEL_RANDOMLY_VOTED_LOG"
- AI remains silent during voting phase (no text generation)
- Uses random.choice() to select from remaining alive players

### 5. `llm_players/llm_constants.py`
**Prompt Updates:**
- **Updated DEFAULT_MODEL** to `"meta-llama/Llama-3.3-70B-Instruct-Turbo"`
- Rewrote `GENERAL_SYSTEM_INFO`:
  - Focus on blending in with humans
  - Mentions AI will be silent during voting (system handles it)
  - Removes all mafia/night phase references
  - Emphasizes natural, casual participation
- Updated `RULES_OF_THE_GAME` reference to use new Social Turing Test rules

### 6. `llm_players/schedule_then_generate_player.py`
**Prompt Refinements:**
- `create_scheduling_prompt()`: Updated to emphasize natural human-like participation
- `create_generation_prompt()`: 
  - Focus on casual, conversational messages
  - Mentions identifying the AI or deflecting suspicion
  - Provides examples of natural player messages
  - Removes mafia-specific language

### 7. `llm_players/llm_wrapper.py`
**Updates:**
- Enhanced Together AI API support with proper error handling
- Improved model loading for direct text generation (non-pipeline mode)
- Better parameter filtering for different model types
- Support for both `use_together` and `use_pipeline` modes

---

## New Files Created

### 8. `web_player.py` ⭐ NEW
**Complete web interface server:**
- Flask-based HTTP server on port 5000
- RESTful API endpoints:
  - `/get_players` - Get available players for a game
  - `/join` - Join game and get session ID
  - `/messages` - Poll for new messages and game state
  - `/send` - Send chat message
  - `/vote` - Cast vote during voting phase
- WebPlayer class manages:
  - Session state per player
  - Message reading with proper UTF-8 encoding
  - Vote submission
  - Player status tracking
- Real-time game state checks (voting phase, game over, etc.)

### 9. `templates/game.html` ⭐ NEW
**Modern web UI:**
- **Login screen**: Game ID input + player name dropdown
- **Game interface**:
  - Phase indicator (Discussion/Voting/Game Over)
  - Scrollable message container with auto-scroll
  - Distinct styling for manager vs chat messages
  - Dynamic input enabling/disabling based on phase
  - Vote buttons during voting phase
  - Real-time updates via polling (1s interval)
- **Visual design**:
  - Gradient purple theme
  - Responsive flexbox layout
  - Smooth animations
  - Color-coded phase indicators
  - Mobile-friendly (900x600 viewport)

### 10. `participants_4players.txt` ⭐ NEW
Example participant list for 4-player games:
```
Alex
Dylan
Hayden
Ronny
```

### 11. Configuration Files ⭐ NEW
- `configurations/3players.json` - 3-player game config
- `configurations/game_4players_anonymous.json` - 4-player with anonymous voting

---

## Key Behavioral Changes

### AI Player Behavior:
1. **During Discussion Phase:**
   - Generates messages using LLM as before
   - Prompts guide it to blend in naturally
   - No mentions of being AI or mafia role
   - Uses Llama-3.3-70B-Instruct-Turbo by default

2. **During Voting Phase:**
   - **Completely silent** (no message generation)
   - Vote is **randomly assigned** by system
   - Cannot vote for itself
   - No LLM reasoning about who to vote for

### Game Flow:
```
INITIALIZE → WAIT FOR PLAYERS
    ↓
  DISCUSSION PHASE (all players chat)
    ↓
  VOTING PHASE (all vote, AI votes randomly & silently)
    ↓
  ELIMINATION (anonymous or public results)
    ↓
  CHECK WIN CONDITIONS:
    - AI eliminated? → Humans Win
    - Only 2 left (AI+1)? → AI Wins
    ↓
  REPEAT (unless game over)
```

### Win Conditions:
- **Humans Win**: AI is successfully identified and eliminated
- **AI Wins**: Survives until only 2 players remain (AI + 1 human)
- **No night kills**, **no mafia team**, **no special roles**

### Anonymous Voting Feature:
- Optional setting enabled via `--anonymous` flag
- When enabled:
  - Individual votes are not shown
  - Only aggregated vote counts displayed
  - Format: "Alex: 2 votes", "Dylan: 1 vote", etc.
- When disabled:
  - Shows who voted for whom: "Alex voted to eliminate Dylan"

---

## What Was NOT Changed

Per the specification, the following were preserved:
- LLM scheduler internals (`llm_players/llm_player.py` core logic)
- LLM generator internals (core inference code)
- Hidden reasoning mechanisms
- Typing delay system
- Chat logging infrastructure
- Message timestamping
- File structure and organization

---

## Technical Improvements

### UTF-8 Encoding Throughout
**Problem**: Windows default encoding (cp1252) caused crashes when reading files with emojis or UTF-8 characters from the web UI.

**Solution**: Updated all file I/O operations in `mafia_main.py`:
- `Player.get_new_messages()` - reading chat files
- `Player.get_voted_player()` - reading vote files
- `get_config()` - reading JSON config
- `voting_sub_phase()` - reading remaining players
- `wait_for_players()` - reading status files
- `get_all_player_out_of_voting_time()` - reading phase status
- `run_chat_round_between_players()` - writing merged chat
- All write operations also use UTF-8

All operations now use: `encoding="utf-8", errors="ignore"`

### Model Updates
- Default model: `meta-llama/Llama-3.3-70B-Instruct-Turbo`
- Together AI API as default provider
- Fallback to local pipeline mode if needed
- Proper parameter handling for different model types

---

## Logging & Metrics

Existing logging captures:
- All messages with timestamps (`all_messages.txt`)
- Vote results per round (in public chat files)
- Player status changes
- LLM decisions and generated content

**Additional metrics available:**
- Number of votes AI received (can be calculated from vote logs)
- Survival rounds (count of discussion phases before elimination)
- Final outcome (stored in `who_wins.txt`)
- Suspicion metric: `votes_for_ai / total_votes`

---

## Usage Examples

### Create Game (Together AI):
```bash
# Install dependencies
pip install -r requirements.txt

# Set up API key
echo "TOGETHER_API_KEY: your-key-here" > .secrets_dict.txt

# Create game with anonymous voting
python prepare_config.py 0001 participants_4players.txt \
  --config_name my_game \
  --anonymous \
  --daytime_minutes 2

# Run game (3 terminals)
python mafia_main.py 0001        # Terminal 1: Game Manager
python web_player.py             # Terminal 2: Web Server
python llm_interface.py 0001     # Terminal 3: AI Player

# Players open browser to http://localhost:5000
```

### Create Game (Local, No API):
```bash
# Install additional dependencies
pip install torch transformers accelerate

# Create config
python prepare_config.py 0001 participants_4players.txt --config_name local_game

# Edit config to set:
# "use_together": false
# "use_pipeline": true

# Run (same as above)
```

---

## Testing Recommendations

1. **Test with minimum players** (3: 1 AI + 2 humans)
2. **Verify win conditions**:
   - AI eliminated → Humans win message
   - 2 players left → AI wins message
3. **Confirm AI voting**:
   - Check logs show random voting
   - Verify AI doesn't vote for itself
   - Ensure no AI messages during voting phase
4. **Check UI terminology**:
   - "AI" (not "Imposter") in elimination messages
   - Discussion phase messages are clear
   - No references to "mafia" or "night" in player-facing text
5. **Test anonymous voting**:
   - Votes shown/hidden correctly based on flag
   - Vote counts accurate
6. **Test web interface**:
   - Login flow works
   - Messages display correctly
   - Phase indicators update
   - Voting buttons appear/disappear correctly
   - UTF-8 characters (emojis) render properly

---

## Player Interface Options

### Terminal-Based (Original):
Each player runs two scripts:
```bash
python player_chat.py 0001    # View messages
python player_input.py 0001   # Send messages/votes
```

### Web-Based (New - Recommended):
Players open browser to `http://localhost:5000`:
- Enter Game ID and select name from dropdown
- Single integrated interface for chat and voting
- Real-time updates
- Phase indicators
- Click-based voting

---

## Configuration Structure

```json
{
  "daytime_minutes": 2,
  "anonymous_voting": true,
  "players": [
    {"name": "Alex", "is_mafia": false},
    {"name": "Dylan", "is_mafia": false},
    {"name": "Hayden", "is_mafia": false},
    {"name": "Ronny", "is_mafia": true}  // AI player
  ],
  "llm_config": {
    "model_name": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "use_together": true,
    "temperature": 1.2,
    "max_tokens": 30
  }
}
```

---

## Summary of All Changes

### Core Game Mechanics:
✅ Removed night phase completely
✅ Only 1 AI player (always "imposter" role)
✅ AI silent during voting (random vote)
✅ New win conditions (AI eliminated OR 2 players remain)
✅ Anonymous voting option

### User Interface:
✅ Web-based interface (Flask + HTML)
✅ Terminal interface still supported
✅ Updated all terminology (Imposter→AI, Mafia→AI)
✅ Phase indicators in web UI
✅ Real-time updates

### Technical:
✅ UTF-8 encoding throughout
✅ Together AI as default provider
✅ Llama-3.3-70B-Instruct-Turbo as default model
✅ Enhanced CLI with more options
✅ Better error handling

### Documentation:
✅ Comprehensive README.md in English
✅ Technical changes documented (this file)
✅ Removed redundant documentation files

---

**Total Files Modified**: 7 core files
**Total Files Created**: 5 new files (web interface, configs, participants)
**Lines of Code Changed**: ~500+
**New Features Added**: Web UI, Anonymous Voting, UTF-8 Support
