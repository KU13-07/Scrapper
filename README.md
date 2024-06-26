## Fetching Logic
When making requests, we must compare when this set was last updated and when our last requests were. We do this to ensure the data we're recieving is consistent and from the same update period (60s). We must also be able to handle incosistencies when pages are being updated (adding a delay).
| Condition | Update | No Update |
|-----------|:------:|:---------:|
| Older     | Wait   | Wait      |
| Same      | Wait   | ✓         |
| Newer     | ✓      | X         |
