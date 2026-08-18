let currentRecordId = null;
let currentFreeCount = 3;

const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const previewSection = document.getElementById('previewSection');
const imagePreview = document.getElementById('imagePreview');
const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const resultSection = document.getElementById('resultSection');
const resultCard = document.getElementById('resultCard');
const downloadBtn = document.getElementById('downloadBtn');
const errorSection = document.getElementById('errorSection');
const errorText = document.getElementById('errorText');
const paymentSection = document.getElementById('paymentSection');
const freeCountDisplay = document.getElementById('freeCount');

uploadArea.addEventListener('click', () => { fileInput.click(); });

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
});

function handleFile(file) {
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) { showError('只支持 JPG、PNG、WEBP 格式'); return; }
    if (file.size > 16 * 1024 * 1024) { showError('文件不能超过16MB'); return; }

    const reader = new FileReader();
    reader.onload = (e) => {
        imagePreview.innerHTML = '<img src="' + e.target.result + '" alt="预览">';
        previewSection.style.display = 'block';
        analyzeBtn.disabled = false;
        uploadArea.dataset.file = file.name;
        uploadArea.dataset.fileData = e.target.result;
    };
    reader.readAsDataURL(file);
    uploadArea.dataset.fileObject = JSON.stringify({ name: file.name, size: file.size, type: file.type });
}

analyzeBtn.addEventListener('click', async () => {
    const fileData = uploadArea.dataset.fileData;
    const fileInfo = JSON.parse(uploadArea.dataset.fileObject || '{}');
    if (!fileData) { showError('请先上传文件'); return; }

    errorSection.style.display = 'none';
    resultSection.style.display = 'none';

    try {
        const formData = new FormData();
        const blob = await (await fetch(fileData)).blob();
        formData.append('file', blob, fileInfo.name);
        const response = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await response.json();

        if (data.need_payment) { paymentSection.style.display = 'block'; return; }
        if (response.ok) {
            currentRecordId = data.record_id;
            currentFreeCount = data.free_count;
            freeCountDisplay.textContent = currentFreeCount;
            progressSection.style.display = 'block';
            analyzeBtn.disabled = true;
            await startAnalysis();
        } else { showError(data.error || '上传失败'); }
    } catch (error) { showError('网络错误：' + error.message); }
});

async function startAnalysis() {
    if (!currentRecordId) return;
    let progress = 0;
    const interval = setInterval(() => {
        progress += 10;
        if (progress <= 90) progressFill.style.width = progress + '%';
    }, 500);

    try {
        const response = await fetch('/api/analyze/' + currentRecordId, { method: 'POST' });
        const data = await response.json();
        clearInterval(interval);
        progressFill.style.width = '100%';
        if (data.need_payment) { paymentSection.style.display = 'block'; return; }
        if (response.ok) {
            progressText.textContent = '分析完成！';
            currentFreeCount = data.free_count;
            freeCountDisplay.textContent = currentFreeCount;
            await generateRepor
