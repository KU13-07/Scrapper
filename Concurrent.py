import asyncio
import time
import math
from Scrapper import Scrapper



async def main() -> None:
    print("start")
    
    scrapper: Scrapper = Scrapper()
    scrapper.start()
    print("2")
    
    while True:
        await asyncio.sleep(10)
    

    
    """
    while True:
        start_time: int = time.time()*1000
        print(f"Start time:\t{start_time}")
        
        last_updated, auctions = await scrapper.get_auctions()
        print(f"Last updated:\t{last_updated}")
        

        # determining time until next
        next_update: int = ((interval + offset) * 1000) - (start_time - last_updated)
        print(f"Timing:\t\t{round((next_update/interval)/10, 2)}%")
        print(f"Next update:\t{next_update}")
        if (next_update <= 0):
            print(f"Defaulting to:\t{offset}")
            next_update = offset * 1000
            
        
        # displays time remaining
        time_display: str = ""
        num_chars: int = 0
        seconds: int = math.floor(next_update/1000) # round down
        
        for i in range(seconds):
            print("\b" * num_chars, end="")
            
            time_display = f"Time remaining:\t{i+1}/{seconds}s"
            num_chars = len(time_display)
            print(time_display, end="")
            
            time.sleep(1)
        time.sleep((next_update - (seconds*1000))/1000)
        print("\b" * num_chars + " " * num_chars, end="\n")
    """
    
    
    

if __name__ == "__main__":
    asyncio.run(main())
    
    
    

    

    


