import asyncio
import json
import announcer
import tts

from config import (
    ENABLE_ANNOUNCER_1,
    ENABLE_ANNOUNCER_2,
    ENABLE_AUDIO_GENERATION,
    ANTHROPIC_API_KEY,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_1,
    ELEVENLABS_VOICE_ID_2,
)

HOST = "127.0.0.1"
PORT = 49123

TEAM_0 = ""
TEAM_1 = ""

SCORE_TEAM_0 = 0
SCORE_TEAM_1 = 0

TIME_REMAINING = 300


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

    print(f"Score updated: Team 0 = {SCORE_TEAM_0}, Team 1 = {SCORE_TEAM_1}")

def updateTime(data: dict):
    global TIME_REMAINING
    TIME_REMAINING = data.get("TimeRemaining", TIME_REMAINING)
    print(f"Time updated: {TIME_REMAINING} seconds remaining")

def updateTeams(data: dict):
    global TEAM_0, TEAM_1

    if TEAM_0 is not "" and TEAM_1 is not "":
        return
    
    gameData = data.get("Game", [])
    teams = gameData.get("Teams", [])
    for team in teams:
        team_num = team.get("TeamNum")
        name = team.get("Name", "")
        if team_num == 0:
            TEAM_0 = name
        elif team_num == 1:
            TEAM_1 = name
    print(f"Teams updated: Team 0 = {TEAM_0}, Team 1 = {TEAM_1}")


async def handle_message(msg: dict):
    global SCORE_TEAM_0, SCORE_TEAM_1
    
    event = msg.get("Event")

    data = msg.get("Data", {})
    if isinstance(data, str):
        data = json.loads(data)

    match event:
        case "MatchInitialized":
            announcerMessage = announcer.agent.invoke(
                {"messages": [{"role": "user", "content": f"New game starting - teams are {TEAM_0} and {TEAM_1}"}]}
            )
            print(announcerMessage["messages"][-1].content)
            if ENABLE_AUDIO_GENERATION:
                tts.speak(announcerMessage["messages"][-1].content, 1)


        case "UpdateState":
            print(f"➕ UpdateState event received")
            updateScore(data)
            updateTime(data)
            updateTeams(data)


        case "GoalScored":
            scorer = data["Scorer"]["Name"]
            team = data["Scorer"]["TeamNum"]
            speed = data["GoalSpeed"]
            remaining_time = 300 - data["GoalTime"]

            print(f"⚽ GOAL by {scorer} ({team}) at {speed:.1f} UU/s!")
            print(f"{data}")

            local_score_team_0 = SCORE_TEAM_0
            local_score_team_1 = SCORE_TEAM_1

            # Add one goal to whatever team scored
            if team == 0:
                local_score_team_0 += 1
            elif team == 1:
                local_score_team_1 += 1

            if scorer and team is not None:
                announcerMessage = announcer.agent.invoke(
                    {"messages": [{"role": "user", "content": f"Goal scored by {scorer} for team ({team}) - the score is now {local_score_team_0} to {local_score_team_1} - remaining time: {remaining_time} seconds"}]}
                )
                print(announcerMessage["messages"][-1].content)
                if ENABLE_AUDIO_GENERATION:
                    tts.speak(announcerMessage["messages"][-1].content, 1)


        case "StatfeedEvent":
            event = data['EventName']
            #player = data['MainTarget']['Name']

            #print(f"Statfeed event: {event} by player {player}")
            print(f"🏅 Statfeed event: {event}")

            if "Goal" in event or event == "Shot":
                return

            if event is not None:
                announcerMessage = announcer.agent.invoke(
                    {"messages": [{"role": "user", "content": f"Statfeed event: {event}"}]}
                )
                print(announcerMessage["messages"][-1].content)
                if ENABLE_AUDIO_GENERATION:
                    tts.speak(announcerMessage["messages"][-1].content, 1)


        case "CrossbarHit":
            player = data['MainTarget']['Name']
            print(f"Crossbar hit by player {player}")
            if player is not None:
                announcerMessage = announcer.agent.invoke(
                    {"messages": [{"role": "user", "content": f"Crossbar hit by player {player}"}]}
                )
                print(announcerMessage["messages"][-1].content)
                if ENABLE_AUDIO_GENERATION:
                    tts.speak(announcerMessage["messages"][-1].content, 1)


        # case "GoalReplayEnd":
        #     print(f"Goal replay ended: data = {data}")
        #     announcerMessage = announcer.agent.invoke(
        #         {"messages": [{"role": "user", "content": f"Short comment about how awesome/cool/amazing/incredible that replay way was"}]}
        #     )
        #     print(announcerMessage["messages"][-1].content)
        #     if ENABLE_AUDIO_GENERATION:
        #         tts.speak(announcerMessage["messages"][-1].content, 1)


        case "MatchEnded":
            winner = data.get("WinnerTeamNum")
            print(f"Match ended: data = {data}")
            team = "Blue" if winner == 0 else "Orange"
            print(f"🎉 Match over! {team} wins!")
            if winner is not None:
                if winner == 0:
                    SCORE_TEAM_0 += 1
                elif winner == 1:
                    SCORE_TEAM_1 += 1


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