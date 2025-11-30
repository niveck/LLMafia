# Social Turing Test Conversion - Implementation Summary

This document summarizes all changes made to convert the LLMafia codebase into a Social Turing Test competitive game.

## Overview

The game has been transformed from a multi-player Mafia game into a Social Turing Test where:
- **ONE AI player** (the "Imposter") tries to blend in with human players
- **All other players are humans** trying to identify the AI
- **No night phase** - only discussion and voting rounds
- **Win conditions**: Humans win if they eliminate the AI; AI wins if only 2 players remain (AI + 1 human)

## Files Modified

### 1. `game_constants.py`
**Changes:**
- Added new role display names: `IMPOSTER_ROLE` = "Imposter", `HUMAN_ROLE` = "Human"
- Updated win messages: `AI_WINS_MESSAGE`, `HUMANS_WIN_MESSAGE`
- Rewrote `RULES_OF_THE_GAME` to explain Social Turing Test mechanics
- Updated all UI messages to use "Discussion Time" instead of "Daytime"
- Changed voting prompt to "Who do you think is the AI?"
- Updated elimination message format
- Added `get_role_display_string()` function for user-facing role names

### 2. `mafia_main.py`
**Major Changes:**
- **Removed night phase entirely**: Deleted `run_nighttime()` function and all references
- **New win conditions** in `is_game_over()`:
  - Humans win: `len(mafia_players) == 0` (AI eliminated)
  - AI wins: `len(players) == 2 and len(mafia_players) == 1`
- **Simplified game loop**: Only runs `run_daytime()` repeatedly until game ends
- Updated `announce_voted_out_player()` to use display role names
- Simplified `notify_players_about_voting_time()` to remove night phase logic

### 3. `prepare_config.py`
**Changes:**
- **Force exactly 1 imposter**: Modified `handle_num_players()` to always set `num_mafia = 1`
- Minimum players changed to 3 (1 AI + 2 humans minimum)
- Removed multi-mafia logic and validation
- The single imposter is randomly selected and will be assigned to the AI

### 4. `llm_interface.py`
**Critical Changes:**
- **Random voting**: Completely rewrote `get_vote_from_llm()`:
  - AI vote is always random (no LLM decision)
  - AI cannot vote for itself
  - No messages or rationale shown during voting
  - Vote is logged as "MODEL_RANDOMLY_VOTED_LOG"
- AI remains silent during voting phase (no text generation)

### 5. `llm_players/llm_constants.py`
**Prompt Updates:**
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

## Key Behavioral Changes

### AI Player Behavior:
1. **During Discussion Phase:**
   - Generates messages using LLM as before
   - Prompts guide it to blend in naturally
   - No mentions of being AI or mafia role

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
  ELIMINATION
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

## What Was NOT Changed

Per the specification, the following were preserved:
- LLM scheduler internals (`llm_players/llm_player.py` core logic)
- LLM generator internals (`llm_players/llm_wrapper.py`)
- Hidden reasoning mechanisms
- Typing delay system
- Chat logging infrastructure
- Message timestamping
- File structure and organization

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
   - "Imposter" and "Human" display correctly
   - Discussion phase messages are clear
   - No references to "mafia" or "night" in player-facing text

## Configuration Example

To create a Social Turing Test game:
```bash
python prepare_config.py -p 5 -l 1 -n participants.txt
```

This creates a game with 5 total players (1 AI, 4 humans). The AI will be randomly assigned the imposter role.

## Notes

- The `-b` (bystander) flag in `prepare_config.py` is now obsolete since there's only 1 role assignment
- Night phase duration parameter (`-nt`) is ignored but kept for backwards compatibility
- The AI always has `is_mafia=True` internally, but displays as "Imposter"
- All humans have `is_mafia=False` internally, but display as "Human"
