import requests
import json
import time
from typing import List

def read_participants(filename: str) -> List[tuple]:
    participants = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip() and not line.startswith('//'):
                # Extract ID from format: Name (ID: 123456) [Game: #ABC123]
                try:
                    id_part = line.split('(ID: ')[1].split(')')[0]
                    participant_id = int(id_part)
                    name = line.split('-')[1].split('(')[0].strip()
                    participants.append((participant_id, name))
                except Exception as e:
                    print(f"Failed to parse line: {line.strip()}")
                    continue
    return participants

def kick_participant(participant_id: int, bounty_id: str, auth_token: str) -> bool:
    url = 'https://api.matcherino.com/__api/bounties/participants/kick'
    headers = {
        'Accept': '*/*',
        'Content-Type': 'text/plain;charset=UTF-8',
        'Origin': 'https://api.matcherino.com',
        'x-mno-auth': f'Bearer {auth_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    
    data = {
        "bountyId": bounty_id,
        "userIds": [participant_id]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return True
        else:
            print(f"Failed to kick participant {participant_id}. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error kicking participant {participant_id}: {str(e)}")
        return False

def main():
    # You'll need to provide your auth token
    auth_token = "***REMOVED***"
    
    # Add the bounty ID here
    bounty_id = 146289
    
    # Read participants from file
    participants = read_participants('unmatched_participants.txt')
    
    print(f"Found {len(participants)} participants to remove")
    
    # Track success and failures
    success_count = 0
    failed_ids = []
    
    # Process each participant
    for participant_id, name in participants:
        print(f"Removing {name} (ID: {participant_id})...")
        
        if kick_participant(participant_id, bounty_id, auth_token):
            success_count += 1
            print(f"Successfully removed {name}")
        else:
            failed_ids.append((participant_id, name))
        
        # Add a small delay between requests to avoid rate limiting
        time.sleep(0.5)
    
    # Print summary
    print("\nRemoval process completed!")
    print(f"Successfully removed: {success_count}")
    print(f"Failed to remove: {len(failed_ids)}")
    
    if failed_ids:
        print("\nFailed participants:")
        for pid, name in failed_ids:
            print(f"- {name} (ID: {pid})")

if __name__ == "__main__":
    main()