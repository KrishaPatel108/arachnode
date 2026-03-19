
### The crawler service is ready to run. Here's exactly what to do it: 

#### First run (takes ~5 minutes to set up):

```
cd crawler-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

#### Verify the pipeline works end-to-end:

```
$ Terminal 1 — start Redis
redis-server

$ Terminal 2 — run the Remotive spider (JSON API, zero scraping complexity)
export JOBSEEKER_ROLE="Backend Engineer"
export JOBSEEKER_STACK="Python,Go,FastAPI,Kubernetes"
scrapy crawl remotive

$ Terminal 3 — watch what comes out
python read_stream.py --count 20

```