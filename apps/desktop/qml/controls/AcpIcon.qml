// Pictogrammes originaux ACP : trait natif, aucune police d'icônes ni ressource distante.
import QtQuick
import Acp.Design

Canvas {
    id: icon
    property string name: "chat"
    property color color: Colors.textSecondary
    property int size: 18
    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Component.onCompleted: requestPaint()
    onPaint: {
        const c = getContext("2d");
        c.reset();
        c.clearRect(0, 0, width, height);
        c.scale(width / 24, height / 24);
        c.strokeStyle = color;
        c.fillStyle = color;
        c.lineWidth = 1.65;
        c.lineCap = "round";
        c.lineJoin = "round";
        function path(points, closed) {
            c.beginPath(); c.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; ++i) c.lineTo(points[i][0], points[i][1]);
            if (closed) c.closePath();
            c.stroke();
        }
        function circle(x, y, radius, filled) {
            c.beginPath(); c.arc(x, y, radius, 0, Math.PI * 2);
            if (filled) c.fill(); else c.stroke();
        }
        switch (name) {
        case "chat":
            path([[5,4],[19,4],[21,6],[21,16],[19,18],[9,18],[4,21],[4,7],[5,4]], true);
            path([[8,9],[17,9]], false); path([[8,13],[14,13]], false); break;
        case "folder":
            path([[3,7],[3,4],[9,4],[12,7],[21,7],[21,19],[3,19],[3,7],[21,7]], false); break;
        case "plus":
            path([[12,5],[12,19]], false); path([[5,12],[19,12]], false); break;
        case "search":
            circle(10.5,10.5,6.5,false); path([[15.5,15.5],[21,21]], false); break;
        case "chevronLeft": path([[15,5],[8,12],[15,19]], false); break;
        case "chevronRight": path([[9,5],[16,12],[9,19]], false); break;
        case "chevronDown": path([[5,9],[12,16],[19,9]], false); break;
        case "close":
            path([[6,6],[18,18]], false); path([[18,6],[6,18]], false); break;
        case "arrowUp":
            path([[12,20],[12,4],[5,11]], false); path([[12,4],[19,11]], false); break;
        case "code":
            path([[8,6],[2,12],[8,18]], false); path([[16,6],[22,12],[16,18]], false);
            path([[14,4],[10,20]], false); break;
        case "check": path([[4,12],[9,17],[20,6]], false); break;
        case "more":
            circle(5,12,1.5,true); circle(12,12,1.5,true); circle(19,12,1.5,true); break;
        case "activity":
            path([[2,12],[6,12],[9,4],[14,20],[17,12],[22,12]], false); break;
        case "archive":
            path([[3,4],[21,4],[21,8],[3,8]], true);
            path([[5,8],[5,20],[19,20],[19,8]], false); path([[9,12],[15,12]], false); break;
        case "grid":
            c.strokeRect(3,3,7,7); c.strokeRect(14,3,7,7);
            c.strokeRect(3,14,7,7); c.strokeRect(14,14,7,7); break;
        case "settings":
            path([[4,6],[20,6]], false); path([[4,12],[20,12]], false); path([[4,18],[20,18]], false);
            circle(9,6,2,false); circle(16,12,2,false); circle(8,18,2,false); break;
        default: circle(12,12,7,false); break;
        }
    }
}
