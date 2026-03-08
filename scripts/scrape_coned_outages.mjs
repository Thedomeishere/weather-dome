#!/usr/bin/env node
/**
 * Scrape per-borough outage data from ConEd outage map using Puppeteer.
 *
 * Strategy:
 * 1. Navigate to the outage map with full browser emulation
 * 2. Intercept all network responses for JSON data containing area breakdowns
 * 3. If XHR interception finds area data, output it
 * 4. Otherwise, try fetching area_data.json using the browser's session cookies
 * 5. Fall back to parsing the DOM report panel
 *
 * Outputs JSON to stdout: [{"area": "Brooklyn", "outages": 20, "customers": 43}, ...]
 * Exits with code 0 on success, 1 on failure.
 */

import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const puppeteer = require('/usr/lib/node_modules/puppeteer');

const DATA_API_BASE = 'https://outagemap.coned.com/resources/data/external/interval_generation_data';
const OUTAGE_MAP_URL = 'https://outagemap.coned.com/outage/';
const TIMEOUT_MS = 20000;

function extractAreaData(json) {
  const results = [];

  // Pattern 1: areaFileData array
  const areas = json.areaFileData || json.file_data || json.areas;
  if (Array.isArray(areas)) {
    for (const area of areas) {
      const name = area.area_name || area.name || '';
      const outages = area.total_outages || area.outages || 0;
      let customers = 0;
      const custA = area.total_cust_a || area.cust_a || 0;
      if (typeof custA === 'object' && custA.val !== undefined) {
        customers = custA.val;
      } else {
        customers = parseInt(custA) || 0;
      }
      if (name) {
        results.push({ area: name, outages, customers });
      }
    }
  }

  // Pattern 2: nested object keyed by area name
  if (results.length === 0) {
    const boroughs = ['Manhattan', 'Brooklyn', 'Bronx', 'Queens', 'Staten Island', 'Westchester',
                      'manhattan', 'brooklyn', 'bronx', 'queens', 'staten_island', 'westchester'];
    for (const key of Object.keys(json)) {
      const normalizedKey = key.replace(/_/g, ' ');
      if (boroughs.some(b => normalizedKey.toLowerCase() === b.toLowerCase())) {
        const val = json[key];
        if (typeof val === 'object' && val !== null) {
          const outages = val.total_outages || val.outages || 0;
          let customers = 0;
          const custA = val.total_cust_a || val.cust_a || val.customers || 0;
          customers = (typeof custA === 'object') ? (custA.val || 0) : (parseInt(custA) || 0);
          results.push({
            area: normalizedKey.charAt(0).toUpperCase() + normalizedKey.slice(1),
            outages,
            customers,
          });
        }
      }
    }
  }

  return results;
}

async function main() {
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
      ],
    });

    const page = await browser.newPage();
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    );
    await page.setExtraHTTPHeaders({
      'Accept-Language': 'en-US,en;q=0.9',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    });

    // Collect area data from any XHR responses
    let xhrResults = [];
    page.on('response', async (response) => {
      const url = response.url();
      if (url.endsWith('.json') && url.includes('data')) {
        try {
          const json = await response.json();
          const extracted = extractAreaData(json);
          if (extracted.length > 0) {
            xhrResults.push(...extracted);
          }
        } catch {
          // skip non-JSON
        }
      }
    });

    // Navigate to the outage map
    await page.goto(OUTAGE_MAP_URL, {
      waitUntil: 'networkidle2',
      timeout: TIMEOUT_MS,
    }).catch(() => {});

    // Wait a bit for any delayed XHR
    await new Promise(r => setTimeout(r, 3000));

    if (xhrResults.length > 0) {
      console.log(JSON.stringify(xhrResults));
      process.exit(0);
    }

    // Strategy 2: Use the browser session to fetch area data files directly
    // The browser may have cookies/tokens that allow access
    try {
      const metaResp = await page.evaluate(async (base) => {
        const r = await fetch(`${base}/metadata.json`);
        return r.ok ? await r.json() : null;
      }, DATA_API_BASE);

      if (metaResp?.directory) {
        // Try known area-level file names
        const areaFiles = ['area_data.json', 'areas.json', 'report.json'];
        for (const file of areaFiles) {
          const data = await page.evaluate(async (url) => {
            try {
              const r = await fetch(url);
              return r.ok ? await r.json() : null;
            } catch { return null; }
          }, `${DATA_API_BASE}/${metaResp.directory}/${file}`);

          if (data) {
            const extracted = extractAreaData(data);
            if (extracted.length > 0) {
              console.log(JSON.stringify(extracted));
              process.exit(0);
            }
          }
        }
      }
    } catch {
      // in-browser fetch failed
    }

    // Strategy 3: Parse DOM for borough-level info
    const domResults = await page.evaluate(() => {
      const results = [];
      const boroughs = ['Manhattan', 'Brooklyn', 'Bronx', 'Queens', 'Staten Island', 'Westchester'];

      // Look for table rows
      for (const row of document.querySelectorAll('tr, [role="row"]')) {
        const cells = row.querySelectorAll('td, th, [role="cell"]');
        if (cells.length >= 2) {
          const name = cells[0]?.textContent?.trim();
          if (name && boroughs.some(b => name.includes(b))) {
            const outages = parseInt(cells[1]?.textContent?.replace(/,/g, '')) || 0;
            const customers = cells.length >= 3 ? (parseInt(cells[2]?.textContent?.replace(/,/g, '')) || 0) : 0;
            results.push({ area: name, outages, customers });
          }
        }
      }

      // Look for any element containing borough names with numbers
      if (results.length === 0) {
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
          if (el.children.length > 0) continue; // only leaf nodes
          const text = el.textContent || '';
          for (const borough of boroughs) {
            if (text.includes(borough) && /\d/.test(text)) {
              const nums = text.match(/[\d,]+/g);
              if (nums) {
                results.push({
                  area: borough,
                  outages: parseInt(nums[0].replace(/,/g, '')) || 0,
                  customers: nums.length >= 2 ? (parseInt(nums[1].replace(/,/g, '')) || 0) : 0,
                });
              }
            }
          }
        }
      }

      return results;
    }).catch(() => []);

    if (domResults.length > 0) {
      console.log(JSON.stringify(domResults));
      process.exit(0);
    }

    console.error('No borough-level outage data found');
    process.exit(1);
  } catch (err) {
    console.error(`Scraper error: ${err.message}`);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}

main();
