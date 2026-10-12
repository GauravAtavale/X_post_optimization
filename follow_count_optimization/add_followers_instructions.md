# Search

("LLM" OR "fine-tuning" OR "RAG" OR "AI agents" OR PyTorch) lang:en since:2026-10-04 -filter:links min_faves:2


# Running instructions

<!-- How to make the HAR file -->

- In Chrome, run your search on x.com and open the Latest tab.
- Open DevTools with Cmd+Option+I and go to the Network tab. Type graphql in the filter box.
- Reload the page, then scroll slowly for as long as you want results. Each scroll loads about 20 more posts.
- Click the download-arrow icon, Export HAR, and save the file into the folder.

Then, offline run:

python parse_x_har.py search.har --max-followers 1000
python parse_x_har.py *.har --min-followers 100 --max-followers 1000 
python parse_x_har.py x_com.har --max-followers 1000 --min-follow-back-ratio 0.8
python parse_x_har.py x_com_new.har --min-follow-back-ratio 0.8


# to start following
python x_follow.py --dry-run     # preview the list, change nothing
python x_follow.py 