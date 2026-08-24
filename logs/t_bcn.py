import asyncio, sys
sys.path.insert(0,'.')
from src.crawlers.norm_detail_crawler import NormDetailCrawler

async def main():
    c = NormDetailCrawler(headless=True)
    await c.start()
    try:
        d = await c.fetch_norm("258171")   # LGSE
        if not d: print("None"); return
        print("tipo:", d.tipo, "| numero:", d.numero)
        print("estado:", d.estado)
        print("titulo:", (d.titulo or "")[:70])
        print("vinculaciones:", str(d.vinculaciones)[:400])
        print("campos:", [k for k in d.__dict__.keys()])
    finally:
        await c.close()

asyncio.run(main())
