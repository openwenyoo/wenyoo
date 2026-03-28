const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const viteDist = path.join(projectRoot, 'editor', 'dist');
const targetJs = path.join(projectRoot, 'static', 'js', 'editor.js');
const targetCss = path.join(projectRoot, 'static', 'css', 'editor.css');
const targetHtml = path.join(projectRoot, 'static', 'editor.html'); // Assuming rename to editor.html if needed

// Clear target files if they exist
if (fs.existsSync(targetJs)) fs.unlinkSync(targetJs);
if (fs.existsSync(targetCss)) fs.unlinkSync(targetCss);
if (fs.existsSync(targetHtml)) fs.unlinkSync(targetHtml);

// Find and copy the hashed JS file
const assetsDir = path.join(viteDist, 'assets');
const files = fs.readdirSync(assetsDir);
const jsFile = files.find(f => f.startsWith('index-') && f.endsWith('.js'));
if (jsFile) {
    fs.copyFileSync(path.join(assetsDir, jsFile), targetJs);
    console.log(`Copied ${jsFile} to ${targetJs}`);
} else {
    console.error('No JS file found in dist/assets');
}

// Find and copy the hashed CSS file
const cssFile = files.find(f => f.startsWith('index-') && f.endsWith('.css'));
if (cssFile) {
    fs.copyFileSync(path.join(assetsDir, cssFile), targetCss);
    console.log(`Copied ${cssFile} to ${targetCss}`);
} else {
    console.error('No CSS file found in dist/assets');
}

// Copy and patch index.html
const sourceHtml = path.join(viteDist, 'index.html');
if (fs.existsSync(sourceHtml)) {
    let htmlContent = fs.readFileSync(sourceHtml, 'utf8');
    
    // Replace JS reference
    htmlContent = htmlContent.replace(/<script type="module" crossorigin src="\/assets\/index-.*?\.js"><\/script>/, '<script type="module" src="static/js/editor.js"></script>');
    
    // Replace CSS reference
    htmlContent = htmlContent.replace(/<link rel="stylesheet" crossorigin href="\/assets\/index-.*?\.css">/, '<link rel="stylesheet" href="static/css/editor.css">');
    
    fs.writeFileSync(targetHtml, htmlContent);
    console.log(`Copied and patched index.html to ${targetHtml}`);
} else {
    console.error('index.html not found in dist');
}

// Optionally copy other files like vite.svg if needed
const svgFile = path.join(viteDist, 'vite.svg');
if (fs.existsSync(svgFile)) {
    const targetSvg = path.join(projectRoot, 'static', 'editor', 'vite.svg');
    fs.copyFileSync(svgFile, targetSvg);
    console.log(`Copied vite.svg to ${targetSvg}`);
}

console.log('Build files copied successfully!');
