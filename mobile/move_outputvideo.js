const { Project } = require('ts-morph');
const project = new Project({
    tsConfigFilePath: '/home/ubuntu/trendsync/mobile/tsconfig.json',
});

const appFile = project.getSourceFileOrThrow('App.tsx');
const outputScreenFile = project.getSourceFileOrThrow('src/screens/OutputScreen.tsx');

const fn = appFile.getFunction('OutputVideo');
if (fn) {
    outputScreenFile.addFunction({
        name: fn.getName(),
        parameters: fn.getParameters().map(p => ({
            name: p.getName(),
            type: p.getTypeNode()?.getText()
        })),
        statements: fn.getBodyText(),
    });
    fn.remove();
    appFile.saveSync();
    outputScreenFile.saveSync();
    console.log('OutputVideo moved');
} else {
    console.log('OutputVideo not found');
}
