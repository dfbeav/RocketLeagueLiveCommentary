"""
An application for generating relevant sports commentary in real time via the official Rocket League API
    Copyright (C) 2026 David Beaver

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""


import asyncio
import json
import announcer
import tts
import time
import random
import sys

from config import (
    ENABLE_ANNOUNCER_1,
    ENABLE_ANNOUNCER_2,
    ENABLE_AUDIO_GENERATION,
)

HOST = "127.0.0.1"
PORT = 49123

from state import (
    TEAM_0,
    TEAM_1,
    SCORE_TEAM_0,
    SCORE_TEAM_1,
    GAME_CLOCK,
    GAME_STARTED,
    IS_OVERTIME,
    TOURNAMENT_BANTER_HAPPENED,
    REPLAY_START_TIME,
    REPLAY_END_TIME
)

def strip_erranwous_json(raw: str) -> str:
    # The announcer prompts instruct the model to reply as a JSON array,
    # e.g. ["Great goal!", "Orange is really struggling."]
    # Strip markdown code fences in case the model wraps the JSON in them.
    stripped = raw
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]  # drop the opening ```json line
    if stripped.endswith("```"):
        stripped = stripped.rsplit("```", 1)[0]  # drop the closing ```
    stripped = stripped.strip()
    return stripped


def trigger_announcer(message, announcersTriggered):

    if announcersTriggered not in ['one', 'two', 'both']:
        return
    

    if (announcersTriggered == 'one' or announcersTriggered == 'both') and ENABLE_ANNOUNCER_1:
        
        announcerMessage = announcer.agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            announcer.get_config(),
            context=announcer.AnnouncerContext(announcer=1)
        )

        processedAnnouncerMessage = strip_erranwous_json(announcerMessage["messages"][-1].content)

        print(f"Announcer 1:{processedAnnouncerMessage}")
        
        if ENABLE_AUDIO_GENERATION:
            tts.speak(processedAnnouncerMessage, 1)


    if (announcersTriggered == 'two' or announcersTriggered == 'both') and ENABLE_ANNOUNCER_2:
        continueMessage = f"Add the color commentary from the previous announcer line, but don't restate anything that was previously mentioned - PREVIOUS MESSAGE: {message}"
        contentValue = continueMessage if announcersTriggered == 'both' else message
        
        announcerMessage = announcer.agent.invoke(
            {"messages": [{"role": "user", "content": contentValue}]},
            announcer.get_config(),
            context=announcer.AnnouncerContext(announcer=2)
        )
        processedAnnouncerMessage = strip_erranwous_json(announcerMessage["messages"][-1].content)
        print(f"Announcer 2:{processedAnnouncerMessage}")
        if ENABLE_AUDIO_GENERATION:
            tts.speak(processedAnnouncerMessage, 2)


def parse_messages(buffer: str):
    # Extract all complete JSON objects from a buffer, return (messages, remainder).

    messages = []
    i = 0
    while i < len(buffer):
        # Skip whitespace
        while i < len(buffer) and buffer[i].isspace():
            i += 1
        if i >= len(buffer):
            break
        decoder = json.JSONDecoder()
        try:
            obj, end_idx = decoder.raw_decode(buffer, i)
            messages.append(obj)
            i += end_idx - i
        except json.JSONDecodeError:
            # Incomplete message — wait for more data
            break
    return messages, buffer[i:]


def update_score(data: dict):
    global SCORE_TEAM_0, SCORE_TEAM_1
    
    local_score_team_0 = 0
    local_score_team_1 = 0

    players = data.get("Players", [])
    for player in players:
        team = player.get("TeamNum")
        if team == 0:
            local_score_team_0 += player.get("Goals", 0)
        elif team == 1:
            local_score_team_1 += player.get("Goals", 0)

    SCORE_TEAM_0 = local_score_team_0
    SCORE_TEAM_1 = local_score_team_1


def handle_time(data: dict):
    global GAME_CLOCK, GAME_STARTED, TEAM_0, TEAM_1, SCORE_TEAM_0, SCORE_TEAM_1, TOURNAMENT_BANTER_HAPPENED
    milestones = [240, 180, 120, 60, 30]
    previous_game_clock = GAME_CLOCK

    GAME_CLOCK = data["Game"]["TimeSeconds"]
    print(f"Time: {GAME_CLOCK} seconds remaining")
    
    if GAME_STARTED and GAME_CLOCK > 0:
        for milestone in milestones:
            if GAME_CLOCK == milestone:
                trigger_announcer(f"{GAME_CLOCK} seconds remaining - Score: {SCORE_TEAM_0} to {SCORE_TEAM_1} - Summarize the match so far", 'both')
                break
    
    else:
        # This is a tournament countdown if the game has not started yet and the clock is counting down
        if GAME_CLOCK >= 30 and GAME_CLOCK < previous_game_clock and not TOURNAMENT_BANTER_HAPPENED:
            trigger_announcer(f"Tournament countdown: {GAME_CLOCK} till game start - Teams: {TEAM_0} and {TEAM_1}", 'one')
            trigger_announcer("Tell a funny story about a Rocket League tournament in your past.", 'two')
            trigger_announcer("React to the most recent comment with a question about their funny story.", 'one')
            trigger_announcer("Answer the question in the previous comment.", 'two')
            # #Only trigger the tournament banter once
            TOURNAMENT_BANTER_HAPPENED = True

    # If it's the last 10 seconds of the game and the score is tied, trigger an announcer alert
    if GAME_CLOCK <= 10 and SCORE_TEAM_0 == SCORE_TEAM_1:
        trigger_announcer(f"It's the last few seconds of the game and the score is tied at {SCORE_TEAM_0} to {SCORE_TEAM_1} - if no one scores, the game will go into overtime!", 'one')


def set_teams(data: dict):
    global TEAM_0, TEAM_1

    if TEAM_0 != "" and TEAM_1 != "":
        return
    
    teams = data["Game"]["Teams"]
    for team in teams:
        team_num = team["TeamNum"]
        name = team["Name"]
        if team_num == 0:
            TEAM_0 = name
        elif team_num == 1:
            TEAM_1 = name
    print(f"Teams updated: Team 0 = {TEAM_0}, Team 1 = {TEAM_1}")


async def handle_message(msg: dict):
    global GAME_STARTED, TEAM_0, TEAM_1, SCORE_TEAM_0, SCORE_TEAM_1, REPLAY_START_TIME, IS_OVERTIME
    
    event = msg.get("Event")

    data = msg.get("Data", {})
    if isinstance(data, str):
        data = json.loads(data)

    match event:

        case "UpdateState":
            update_score(data)
            handle_time(data)
            set_teams(data)
            if data["Game"]["bOvertime"] == True:
                IS_OVERTIME = True


        case "MatchInitialized":
            GAME_STARTED = True
            trigger_announcer(f"New game starting - teams are {TEAM_0} and {TEAM_1}", 'both')


        case "GoalScored":
            scorer = data["Scorer"]["Name"]
            team = data["Scorer"]["TeamNum"]
            speed = data["GoalSpeed"]
            remaining_time = 300 - data["GoalTime"]

            print(f"⚽ GOAL by {scorer} ({team}) at {speed:.1f} UU/s!")
            print(f"Speed: {speed:.1f}")
            print(f"Remaining time: {remaining_time} seconds")

            local_score_team_0 = SCORE_TEAM_0
            local_score_team_1 = SCORE_TEAM_1

            # Add one goal to whatever team scored (score state does not update until tick after the goal event)
            if team == 0:
                local_score_team_0 += 1
            elif team == 1:
                local_score_team_1 += 1

            if scorer and team is not None:
                trigger_announcer(f"Goal scored by {scorer} for team ({team}) - the score is now {local_score_team_0} to {local_score_team_1} - remaining time: {remaining_time} seconds", 'both')


        case "StatfeedEvent":
            event = data['EventName']
            player = data['MainTarget']['Name']
            team = data['MainTarget']['TeamNum']
            teamName = TEAM_0 if team == 0 else TEAM_1

            #print(f"Statfeed event: {event} by player {player}")

            if "Goal" in event or event == "Shot" or event == "HatTrick":
                return

            if event is not None:
                print(f"Statfeed event: {data}")
                trigger_announcer(f"Statfeed event: {event} by player {player} for team {teamName}", 'one')


        case "CrossbarHit":
            player = data['BallLastTouch']['Player']['Name']
            print(f"Crossbar hit by player {player}")
            if player is not None:
                trigger_announcer(f"Crossbar hit by player {player}", 'one')


        case "GoalReplayStart":
            #save time to REPLAY_START_TIME 
            REPLAY_START_TIME = time.time()


        case "GoalReplayEnd":
            REPLAY_END_TIME = time.time()

            REPLAY_DURATION = REPLAY_END_TIME - REPLAY_START_TIME

            print(f'Replay duration: {REPLAY_DURATION} seconds')

            # If REPLAY_DURATION is shorter than 5 seconds, skip the replay commentary
            if REPLAY_DURATION < 5:
                return
            
            # Randomly decide whether to trigger a comment about the replay
            trigger_comment = random.choice([True, False])

            if trigger_comment == True:
                trigger_announcer(f"Short 2-4 word vague comment about the replay: 'That's a beautiful goal.' / 'That replay was incredible.' / 'Amazing shot there.'", 'two')

            REPLAY_START_TIME = 0
            REPLAY_END_TIME = 0


        case "CountdownBegin":
            if IS_OVERTIME:
                trigger_announcer("Heading into overtime! First goal wins the game. Convey excitement!", "both")


        case "MatchEnded":
            winner = data.get("WinnerTeamNum")
            print(f"Match ended: data = {data}")
            team = TEAM_0 if winner == 0 else TEAM_1
            print(f"🎉 Match over! {team} wins!")
            if winner is not None:
                trigger_announcer(f"Match ended - final score: {SCORE_TEAM_0} to {SCORE_TEAM_1}", 'both')
                trigger_announcer("Signoff and thank you for watching!", 'one')

            announcer.reset_match()
            GAME_STARTED = False


        case _:
            pass # print(f"[{event}]", data)


async def main():
    print("""
        RocketLeagueLiveCommentary  Copyright (C) 2026  David Beaver
          
        This program comes with ABSOLUTELY NO WARRANTY.
        This is free software, and you are welcome to redistribute it
        under certain conditions.
          
        You should have received a copy of the GNU General Public License
        along with this program.  If not, see <https://www.gnu.org/licenses/>.
          
          """)


    # Check command-line arguments for `show w` and `show c`
    if len(sys.argv) > 1:
        if sys.argv[1] == "show" and len(sys.argv) > 2:
            if sys.argv[2] == "w":
                show_w()
                return
            elif sys.argv[2] == "c":
                show_c()
                return

    print(f"Connecting to {HOST}:{PORT}...")
    reader, writer = await asyncio.open_connection(HOST, PORT)
    print("Connected! Waiting for events...\n")

    buffer = ""
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                print("Connection closed by game.")
                break

            buffer += chunk.decode("utf-8")
            messages, buffer = parse_messages(buffer)
            for msg in messages:
                await handle_message(msg)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("Shutting down...")
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())