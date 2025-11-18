const fs = require('fs');
const path = require('path');

// Configuration: The folder containing your JSON files
const folderName = 'foxnews_transcripts_utterances';
const directoryPath = path.join(__dirname, folderName);

function countShortUtterances() {
    try {
        // 1. Check if directory exists
        if (!fs.existsSync(directoryPath)) {
            console.error(`Error: Directory "${folderName}" not found.`);
            return;
        }

        // 2. Read all files in the directory
        const files = fs.readdirSync(directoryPath);
        
        let matchingFilesCount = 0;
        let processedFiles = 0;
        let filesWithErrors = 0;

        console.log(`Scanning ${files.length} files...`);

        // 3. Iterate through files
        files.forEach(file => {
            // Only process .json files
            if (path.extname(file).toLowerCase() === '.json') {
                const filePath = path.join(directoryPath, file);

                try {
                    const fileData = fs.readFileSync(filePath, 'utf8');
                    const jsonContent = JSON.parse(fileData);

                    // 4. Check the condition: utterances exists AND length is < 5
                    if (Array.isArray(jsonContent.utterances) && jsonContent.utterances.length < 5) {
                        matchingFilesCount++;
                        // Optional: Print the filename if you want to see which ones match
                        // console.log(`Found: ${file} (Count: ${jsonContent.utterances.length})`);
                    }
                    
                    processedFiles++;

                } catch (parseError) {
                    console.error(`Error parsing ${file}: ${parseError.message}`);
                    filesWithErrors++;
                }
            }
        });

        // 5. Output results
        console.log('------------------------------------------------');
        console.log(`Total JSON files processed: ${processedFiles}`);
        console.log(`Files with parse errors:    ${filesWithErrors}`);
        console.log(`Files with < 5 utterances:  ${matchingFilesCount}`);
        console.log('------------------------------------------------');

    } catch (err) {
        console.error('Unable to scan directory: ' + err);
    }
}

countShortUtterances();