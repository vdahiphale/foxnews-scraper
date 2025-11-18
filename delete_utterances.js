const fs = require('fs');
const path = require('path');

// Configuration: The folder containing your JSON files
const folderName = 'foxnews_transcripts_utterances';
const directoryPath = path.join(__dirname, folderName);

function deleteShortUtteranceFiles() {
    try {
        // 1. Check if directory exists
        if (!fs.existsSync(directoryPath)) {
            console.error(`Error: Directory "${folderName}" not found.`);
            return;
        }

        // 2. Read all files in the directory
        const files = fs.readdirSync(directoryPath);
        
        let deletedFilesCount = 0;
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

                    // 4. Check condition: utterances exists AND length is <= 5
                    if (Array.isArray(jsonContent.utterances) && jsonContent.utterances.length <= 5) {
                        
                        // DELETE ACTION
                        fs.unlinkSync(filePath);
                        
                        console.log(`[DELETED] ${file} (Utterances: ${jsonContent.utterances.length})`);
                        deletedFilesCount++;
                    }
                    
                    processedFiles++;

                } catch (err) {
                    console.error(`Error processing ${file}: ${err.message}`);
                    filesWithErrors++;
                }
            }
        });

        // 5. Output results
        console.log('------------------------------------------------');
        console.log(`Total JSON files scanned:   ${processedFiles}`);
        console.log(`Files with parse errors:    ${filesWithErrors}`);
        console.log(`Total files DELETED:        ${deletedFilesCount}`);
        console.log('------------------------------------------------');

    } catch (err) {
        console.error('CRITICAL ERROR: ' + err);
    }
}

deleteShortUtteranceFiles();