## Fetching
When making requests, we must compare when this set was last updated and when our last requests were. We do this to ensure the data we're recieving is consistent and from the same update period (60s). We must also be able to handle incosistencies when pages are being updated (adding a delay).
| Condition | Update | No Update |
|-----------|:------:|:---------:|
| Older     | Wait   | Wait      |
| Same      | Wait   | ✓         |
| Newer     | ✓      | X         |
<br />

## New Auctions
In order to avoid completely rescrapping all pages of auctions data, we can start from the beginning until we've found an old auction. This works because new auctions are prepended, however non-bins will retain the same position in the list. So in we can start from the beginning, grab all auctions until we reach an existing auction that is a bin, and ignore repeating non-bins.
<br />

## Item-Specific vs. Category-Specific Attributes
Usually items will fall under a category such as "bow", "sword", "helmet"... However, on occasion, despite being in a category, items may have item specific attributes. To prevent this attribute from being shown as a possibility for all items within the category, we must seperate item-specific and category-specific.
| Item                            | Category                             |
|---------------------------------|--------------------------------------|
| More detailed data              | Potentially inaccurate item data     |
| Potentially incomplete data set | More developed data                  |
| Much larger memory usage        | Smaller memory and perfomance impact |

### Current Approach
Hard code known common attributes lol.
