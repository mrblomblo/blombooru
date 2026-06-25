const DICE_FACE_DOTS = {
    1: '<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"></circle>',
    2: '<circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"></circle>',
    3: '<circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"></circle>',
    4: '<circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="8" cy="16" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"></circle>',
    5: '<circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="8" cy="16" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"></circle>',
    6: '<circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="8" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="8" cy="12" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="12" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="8" cy="16" r="1.5" fill="currentColor" stroke="none"></circle><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"></circle>'
};

function renderDiceIcon(face) {
    const resolvedFace = face || Math.floor(Math.random() * 6) + 1;
    const dots = DICE_FACE_DOTS[resolvedFace] || DICE_FACE_DOTS[1];

    return `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>${dots}</svg>`;
}
