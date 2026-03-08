#!/usr/bin/env node
/**
 * Scrape per-borough outage data from ConEd outage map using Puppeteer.
 *
 * Outputs JSON to stdout: [{"area": "Brooklyn", "outages": 20, "customers": 43}, ...]
 * Exits with code 0 on success, 1 on failure.
 */

import puppeteer from 'puppeteer';

const OUTAGE_MAP_URL = 'https://outagemap.coned.com/outage/';
const TIMEOUT_MS = 20000;

async function scrapeViaXHR(page) {
  // Intercept XHR responses that contain per-area outage data
  return new Promise((resolve, reject) => {
    const results = [];
    let resolved = false;

    page.on('response', async (response) => {
      if (resolved) return;
      const url = response.url();
      // Look for area-specific data files (e.g., areaFileData, per-area JSON)
      if (url.includes('data/external/') && url.endsWith('.json') && !url.includes('metadata')) {
        try {
          const json = await response.json();
          // Check for area-level file data (individual borough files)
          if (json.areaFileData) {
            const areas = json.areaFileData;
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
          }
          // Check for file_data with areas array
          if (json.file_data && Array.isArray(json.file_data)) {
            for (const entry of json.file_data) {
              const name = entry.area_name || entry.name || '';
              const outages = entry.total_outages || entry.outages || 0;
              let customers = 0;
              const custA = entry.total_cust_a || entry.cust_a || 0;
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
        } catch {
          // Not JSON or parse error, skip
        }
      }
    });

    // Wait for page to load and XHR to fire
    setTimeout(() => {
      resolved = true;
      if (results.length > 0) {
        resolve(results);
      } else {
        reject(new Error('No XHR area data intercepted'));
      }
    }, 12000);
  });
}

async function scrapeViaDOM(page) {
  // Parse the report panel DOM for borough-level tables/rows
  return await page.evaluate(() => {
    const results = [];

    // Strategy 1: Look for borough rows in the outage report table
    const rows = document.querySelectorAll(
      '.report-table tr, .outage-table tr, .area-row, [class*="area"] tr, [class*="borough"] tr'
    );
    for (const row of rows) {
      const cells = row.querySelectorAll('td, th');
      if (cells.length >= 2) {
        const name = cells[0]?.textContent?.trim();
        const boroughs = ['Manhattan', 'Brooklyn', 'Bronx', 'Queens', 'Staten Island', 'Westchester'];
        if (name && boroughs.some(b => name.includes(b))) {
          const outages = parseInt(cells[1]?.textContent?.replace(/,/g, '')) || 0;
          const customers = cells.length >= 3 ? (parseInt(cells[2]?.textContent?.replace(/,/g, '')) || 0) : 0;
          results.push({ area: name, outages, customers });
        }
      }
    }

    // Strategy 2: Look for list items with borough names and numbers
    if (results.length === 0) {
      const elements = document.querySelectorAll(
        '[class*="area"], [class*="borough"], [class*="region"], .panel-body li, .report li'
      );
      for (const el of elements) {
        const text = el.textContent || '';
        const boroughs = ['Manhattan', 'Brooklyn', 'Bronx', 'Queens', 'Staten Island', 'Westchester'];
        for (const borough of boroughs) {
          if (text.includes(borough)) {
            const nums = text.match(/[\d,]+/g);
            if (nums && nums.length >= 1) {
              const outages = parseInt(nums[0].replace(/,/g, '')) || 0;
              const customers = nums.length >= 2 ? (parseInt(nums[1].replace(/,/g, '')) || 0) : 0;
              results.push({ area: borough, outages, customers });
            }
          }
        }
      }
    }

    return results;
  });
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
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    // Try XHR interception first
    let results = [];
    try {
      const xhrPromise = scrapeViaXHR(page);
      await page.goto(OUTAGE_MAP_URL, { waitUntil: 'networkidle2', timeout: TIMEOUT_MS });
      results = await xhrPromise;
    } catch {
      // XHR interception failed, try DOM parsing
      try {
        await page.waitForSelector('body', { timeout: 5000 });
        results = await scrapeViaDOM(page);
      } catch {
        // DOM parsing also failed
      }
    }

    if (results.length > 0) {
      console.log(JSON.stringify(results));
      process.exit(0);
    } else {
      console.error('No borough-level outage data found');
      process.exit(1);
    }
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
