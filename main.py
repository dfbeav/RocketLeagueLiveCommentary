import asyncio
import json
import announcer
import tts
import time
import random

from config import (
    ENABLE_ANNOUNCER_1,
    ENABLE_ANNOUNCER_2,
    ENABLE_AUDIO_GENERATION,
    SYSTEM_PROMPT_1,
    SYSTEM_PROMPT_2,
)

HOST = "127.0.0.1"
PORT = 49123

TEAM_0 = ""
TEAM_1 = ""

SCORE_TEAM_0 = 0
SCORE_TEAM_1 = 0

TIME_REMAINING = 300

REPLAY_START_TIME = 0
REPLAY_END_TIME = 0


def triggerAnnouncers(message, announcersTriggered):
    if announcersTriggered not in ['one', 'two', 'both']:
        return
    

    if (announcersTriggered == 'one' or announcersTriggered == 'both') and ENABLE_ANNOUNCER_1:
        
        announcerMessage = announcer.agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            announcer.get_config(),
            context=announcer.AnnouncerContext(announcer=1)
        )
        
        if ENABLE_AUDIO_GENERATION:
            tts.speak(announcerMessage["messages"][-1].content, 1)


    if (announcersTriggered == 'two' or announcersTriggered == 'both') and ENABLE_ANNOUNCER_2:
        continueMessage = f"Add the color commentary from the previous announcer line, but don't restate anything that was previously mentioned - PREVIOUS MESSAGE: {message}"
        contentValue = continueMessage if announcersTriggered == 'both' else message
        
        announcerMessage = announcer.agent.invoke(
            {"messages": [{"role": "user", "content": contentValue}]},
            announcer.get_config(),
            context=announcer.AnnouncerContext(announcer=2)
        )
        
        if ENABLE_AUDIO_GENERATION:
            tts.speak(announcerMessage["messages"][-1].content, 2)


def parse_messages(buffer: str):
    """Extract all complete JSON objects from a buffer, return (messages, remainder)."""
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


def updateScore(data: dict):
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


def updateTime(data: dict):
    global TIME_REMAINING
    milestones = [240, 180, 120, 60, 30]

    TIME_REMAINING = data["Game"]["TimeSeconds"]
    print(f"Time: {TIME_REMAINING} seconds remaining")
    for milestone in milestones:
        if TIME_REMAINING == milestone:
            triggerAnnouncers(f"{TIME_REMAINING} seconds remaining - Score: {SCORE_TEAM_0} to {SCORE_TEAM_1} - Summarize the match so far", 'both')
            break


def updateTeams(data: dict):
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
    global SCORE_TEAM_0, SCORE_TEAM_1, REPLAY_START_TIME
    
    event = msg.get("Event")

    data = msg.get("Data", {})
    if isinstance(data, str):
        data = json.loads(data)

    match event:
        case "MatchInitialized":
            announcer.reset_match()
            triggerAnnouncers(f"New game starting - teams are {TEAM_0} and {TEAM_1}", 'both')


        case "UpdateState":
            updateScore(data)
            updateTime(data)
            updateTeams(data)


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

            # Add one goal to whatever team scored
            if team == 0:
                local_score_team_0 += 1
            elif team == 1:
                local_score_team_1 += 1

            if scorer and team is not None:
                triggerAnnouncers(f"Goal scored by {scorer} for team ({team}) - the score is now {local_score_team_0} to {local_score_team_1} - remaining time: {remaining_time} seconds", 'both')


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
                triggerAnnouncers(f"Statfeed event: {event} by player {player} for team {teamName}", 'one')


        case "CrossbarHit":
            player = data['BallLastTouch']['Player']['Name']
            print(f"Crossbar hit by player {player}")
            if player is not None:
                triggerAnnouncers(f"Crossbar hit by player {player}", 'one')


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
                triggerAnnouncers(f"Short 2-4 word vague comment about the replay: 'That's a beautiful goal.' / 'That replay was incredible.' / 'Amazing shot there.'", 'two')

            REPLAY_START_TIME = 0
            REPLAY_END_TIME = 0


        case "MatchEnded":
            winner = data.get("WinnerTeamNum")
            print(f"Match ended: data = {data}")
            team = TEAM_0 if winner == 0 else TEAM_1
            print(f"🎉 Match over! {team} wins!")
            if winner is not None:
                triggerAnnouncers(f"Match ended - final score: {SCORE_TEAM_0} to {SCORE_TEAM_1}", 'both')


        case _:
            pass # print(f"[{event}]", data)


async def main():
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