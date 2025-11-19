const fs = require('fs');
const path = require('path');

// Configuration
const inputDir = path.join(__dirname, 'foxnews_transcripts_utterances');
const outputDir = path.join(__dirname, 'foxnews_transcripts_utterances_Modifies');

// regex to match the specific ad code block
// It looks for "if (window && window.foxstrike" ... all the way to ... "console.error('Error: window.foxstrike not found'); }"
const garbageRegex = /if\s*\(window\s*&&\s*window\.foxstrike[\s\S]*?\}\s*else\s*\{\s*console\.error\('Error: window\.foxstrike not found'\);\s*\}/g;

// Ensure output directory exists
if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir);
    console.log(`Created output directory: ${outputDir}`);
}

// Read all files in the input directory
fs.readdir(inputDir, (err, files) => {
    if (err) {
        return console.error('Unable to scan directory: ' + err);
    }

    let processedCount = 0;

    files.forEach((file) => {
        // Only process JSON files
        if (path.extname(file).toLowerCase() === '.json') {
            const inputPath = path.join(inputDir, file);
            const outputPath = path.join(outputDir, file);

            try {
                // 1. Read the file
                const rawData = fs.readFileSync(inputPath, 'utf8');
                const jsonData = JSON.parse(rawData);

                // 2. Clean the utterances
                if (jsonData.utterances && Array.isArray(jsonData.utterances)) {
                    jsonData.utterances = jsonData.utterances.map(utterance => {
                        if (utterance.sentences) {
                            // Replace the garbage code with an empty string and trim extra whitespace
                            utterance.sentences = utterance.sentences.replace(garbageRegex, '').trim();
                        }
                        return utterance;
                    });
                }

                // 3. Write to the new folder
                // null, 2 is used to pretty-print the JSON so it is readable
                fs.writeFileSync(outputPath, JSON.stringify(jsonData, null, 2));
                
                console.log(`Processed: ${file}`);
                processedCount++;

            } catch (e) {
                console.error(`Error processing file ${file}:`, e);
            }
        }
    });

    console.log('------------------------------------------------');
    console.log(`Completed! ${processedCount} files saved to ${outputDir}`);
});