const fs = require("fs");
const path = require("path");
const axios = require("axios");
const cheerio = require("cheerio");

// Headers for HTTP requests
const headers = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36",
};

// Function to sanitize filenames
const sanitizeFilename = (filename) => {
  return filename.replace(/[<>:"/\\|?*]/g, "-").substring(0, 100);
};

/**
 * Scrapes a Fox News article page.
 * @param {string} url - The URL of the article to scrape.
 * @returns {Promise<object>} - An object containing the scraped data or an error.
 */
const scrapeFoxNewsArticle = async (url) => {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await axios.get(url, { headers });
      if (response.status === 200) {
        const $ = cheerio.load(response.data);

        const headline =
          $("h1.headline").text().trim() || "No headline found";
        
        // The sub-headline (description) isn't reliably on the article page itself.
        // We'll grab it from the API in the main loop and add it to the final JSON.
        // This function will just provide a default.
        const subHeadline = "No sub-headline found on article page";

        const utterances = [];
        let bodyText = "";
        
        const articleBody = $("div.article-body");

        if (articleBody.length > 0) {
            let lines = [];
            const preElement = articleBody.find('pre');
            
            if (preElement.length > 0) {
                bodyText = preElement.text();
                lines = bodyText.split(/\r?\n/);
            } else {
                const html = articleBody.html() || "";
                // Convert all paragraph and break tags to a consistent newline format
                const textWithNewlines = html.replace(/<p[^>]*>/gi, '\n').replace(/<\/p>/gi, '').replace(/<br\s*\/?>/gi, '\n');
                // Use cheerio to strip any remaining HTML and decode entities
                bodyText = $('<div>').html(textWithNewlines).text();
                lines = bodyText.split(/\r?\n/);
            }

            const speakerRegex = /^([A-Z][A-Z\s.,'()-]+):(.*)$/s;
            let lastUtterance = null;

            for (const line of lines) {
                const text = line.trim();

                if (!text || text.startsWith('[') || text.startsWith('(')) {
                    continue;
                }

                const match = text.match(speakerRegex);
                if (match && match[1] && match[2]) {
                    const speaker = match[1].trim();
                    const sentences = match[2].trim();
                    if (sentences) {
                        lastUtterance = {
                            speaker,
                            sentences,
                            timeStamp: "",
                            isLastSentenceInterrupted: false,
                            isQuestion: false,
                            isAnswer: false,
                        };
                        utterances.push(lastUtterance);
                    }
                } else if (lastUtterance) {
                    const lowerText = text.toLowerCase();
                    const isNarration = lowerText.includes('voice-over') || lowerText.includes('on camera') || lowerText.includes('begin video') || lowerText.includes('end video');
                    if (!isNarration) {
                        lastUtterance.sentences += " " + text;
                    } else {
                        lastUtterance = null;
                    }
                }
            }
        } else {
          // Fallback if no body text is found in expected formats
          bodyText = "No body text found";
        }

        const articleBodyParagraphs = $('div.article-body p');
        let lastUtterance = null;
        const speakerRegex = /^([A-Z][a-zA-Z\s.,'()-]+):(.*)$/;

        if (articleBodyParagraphs.length > 0) {
            articleBodyParagraphs.each((i, p) => {
                const p_html = $(p).html();
                const lines = p_html.split(/<br\s*\/?>/i).map(line => {
                    return $('<div>' + line + '</div>').text().trim();
                });

                for (const text of lines) {
                    if (!text || text.startsWith('[') || text.startsWith('(')) {
                        continue;
                    }
                    
                    const match = text.match(speakerRegex);
                    if (match) {
                        const speaker = match[1].trim();
                        const utteranceText = match[2].trim();
                        lastUtterance = { speaker, utterance: utteranceText };
                        utterances.push(lastUtterance);
                    } else if (lastUtterance) {
                        lastUtterance.utterance += ' ' + text;
                    }
                }
            });
        }

        // Check for <pre> element if no paragraphs found or no utterances were extracted
        if (utterances.length === 0) {
            const preElement = $('pre');
            if (preElement.length > 0) {
                const bodyText = preElement.text();
                const lines = bodyText.split(/\r?\n/);
                const speakerRegex = /^([A-Z][a-zA-Z\s.,'-()]+):(.*)$/;
                let lastUtterance = null;

                for (const line of lines) {
                    const trimmedLine = line.trim();
                    if (!trimmedLine || trimmedLine.startsWith('[')) continue;

                    const match = trimmedLine.match(speakerRegex);
                    if (match) {
                        const speaker = match[1].trim();
                        const text = match[2].trim();
                        lastUtterance = { speaker, utterance: text };
                        utterances.push(lastUtterance);
                    } else if (lastUtterance) {
                        lastUtterance.utterance += ' ' + trimmedLine;
                    }
                }
            }
        }

        return {
          headline,
          subHeadline, // This will be overwritten by the main loop's API data
          bodyText: bodyText || "No body text found",
          utterances,
        };
      } else {
        console.log(
          `Attempt ${attempt + 1} failed with status code: ${response.status}`
        );
        await new Promise((r) => setTimeout(r, 2000));
      }
    } catch (error) {
      console.log(`Attempt ${attempt + 1} failed for ${url} with error: ${error.message}`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  return { error: `Failed to retrieve the article after multiple attempts: ${url}` };
};

// Directories for saving files
const transcriptFolder = "foxnews_transcripts_text";
const htmlFolder = "foxnews_transcripts_html";
const utterancesFolder = "foxnews_transcripts_utterances";
fs.mkdirSync(transcriptFolder, { recursive: true });
fs.mkdirSync(htmlFolder, { recursive: true });
fs.mkdirSync(utterancesFolder, { recursive: true });

// --- Main Scraper Loop ---
// Start from offset 0 (page 1)
let currentOffset = 9724;
const pageSize = 11; // Use the size from your example

console.log("Started scraping Fox News transcripts from API");

(async () => {
  while (true) {
    const baseUrl = `https://www.foxnews.com/api/article-search?searchBy=categories&values=fox-news%2Ftranscript&size=${pageSize}&from=${currentOffset}`;
    console.log(`\n--- Scraping transcript list from API offset: ${currentOffset} ---`);

    let articles;
    try {
      const response = await axios.get(baseUrl, { headers });
      if (response.status !== 200) {
        console.log(
          `Failed to access API at offset ${currentOffset}. Status: ${response.status}. Stopping.`
        );
        break;
      }

      articles = response.data;

      if (!articles || !articles.length) {
        console.log(`No more transcripts found at offset ${currentOffset}. Scraping complete.`);
        break;
      }
    } catch (error) {
      console.log(
        `Error accessing the Fox News API at offset ${currentOffset}: ${error.message}. Stopping.`
      );
      break;
    }

    for (const article of articles) {
      const headline = article.title ? article.title.trim() : "No Title";
      const articleUrl = article.url;
      const dateStr = article.publicationDate 
        ? new Date(article.publicationDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
        : "Unknown Date";
      const subHeadline = article.description ? article.description.trim() : "No sub-headline found";

      if (!articleUrl || !headline) {
        console.log("Skipping article with missing URL or headline.");
        continue;
      }

      // Handle potentially relative URLs
      const fullArticleUrl = new URL(articleUrl, "https://www.foxnews.com").href;

      const filenameBase = sanitizeFilename(`${dateStr} - ${headline}`);
      const textFilename = `${filenameBase}.txt`;
      const htmlFilename = `${filenameBase}.html`;
      const utterancesFilename = `${filenameBase}.json`;

      // Check if file already exists to avoid re-scraping
      const textFilePath = path.join(transcriptFolder, textFilename);
      if (fs.existsSync(textFilePath)) {
          console.log(`Skipping already saved transcript: ${textFilename}`);
          continue;
      }

      console.log(`Scraping article: ${headline} (${dateStr})`);
      const articleData = await scrapeFoxNewsArticle(fullArticleUrl);

      if (articleData.error) {
        console.log(`Error scraping article: ${articleData.error}`);
      } else {
        // Prepare HTML content
        const htmlContent = `
          <html>
            <head><title>${articleData.headline}</title></head>
            <body>
              <h1>${articleData.headline}</h1>
              <h2>${subHeadline}</h2>
              <pre>${articleData.bodyText}</pre>
            </body>
          </html>
        `;

        // Prepare text content
        // Use the headline from the scraped page, but the sub-headline from the API
        const articleText = `Headline: ${articleData.headline}\nSub-headline: ${subHeadline}\n\n${articleData.bodyText}`;

        // Save HTML file
        const htmlFilePath = path.join(htmlFolder, htmlFilename);
        fs.writeFileSync(htmlFilePath, htmlContent, "utf8");
        console.log(`Saved HTML transcript to: ${htmlFilePath}`);

        // Save text file
        fs.writeFileSync(textFilePath, articleText, "utf8");
        console.log(`Saved text transcript to: ${textFilePath}`);

        // Save utterances to JSON file
        const utterancesFilePath = path.join(
          utterancesFolder,
          utterancesFilename
        );
        
        // We use the headline from the scraped page (articleData.headline)
        // but the subHeadline from the API (subHeadline)
        const jsonTranscript = {
          date: dateStr,
          headline: articleData.headline,
          subHeadline: subHeadline, 
          url: fullArticleUrl,
          isInterview: false, // You can set this to true if you add logic to detect it
          utterances: articleData.utterances,
        };
        fs.writeFileSync(
          utterancesFilePath,
          JSON.stringify(jsonTranscript, null, 2),
          "utf8"
        );
        console.log(`Saved utterances to: ${utterancesFilePath}`);
      }

      // Be polite with requests
      await new Promise((r) => setTimeout(r, 1000));
    }

    // Move to the next page
    currentOffset += pageSize;
  }
})();