const { Project } = require('ts-morph');
const fs = require('fs');
const path = require('path');

const project = new Project({
    tsConfigFilePath: '/home/ubuntu/trendsync/mobile/tsconfig.json',
});

const appFile = project.getSourceFileOrThrow('App.tsx');
const typesFile = project.getSourceFileOrThrow('src/types.ts');

const utilsDir = '/home/ubuntu/trendsync/mobile/src/utils';
fs.mkdirSync(utilsDir, { recursive: true });

const helpersFile = project.createSourceFile(path.join(utilsDir, 'helpers.ts'), '', { overwrite: true });

// Move types to types.ts
const typesToMove = ['AppView', 'ProjectFilter', 'ProjectSort', 'ProjectAction'];
typesToMove.forEach(typeName => {
    const typeAlias = appFile.getTypeAlias(typeName);
    if (typeAlias) {
        typesFile.addTypeAlias({
            name: typeAlias.getName(),
            type: typeAlias.getTypeNode().getText(),
            isExported: true
        });
        typeAlias.remove();
    }
});

// Move constants
const constantsToMove = [
    'busyPhases', 'planningPhases', 'defaultRenderOptions', 'VIDEO_LENGTH_PRESETS',
    'projectFilters', 'projectSorts', 'LANGUAGES', 'LLM_PROVIDERS', 'providerModelPlaceholders',
    'tripContextFields'
];

// Helper functions to move
const functionsToMove = [
    'formatTimestamp', 'fallbackSegmentId', 'segmentForDecision', 'windowForDecision',
    'projectTitle', 'sessionTitle', 'phaseLabel', 'phaseFilter', 'phaseTone', 'formatUpdatedAt'
];

helpersFile.addImportDeclaration({
    namedImports: ['ProjectSummary', 'TripSession', 'TripPhase', 'ProjectFilter', 'ProjectSort', 'ProjectAction', 'RenderOptions', 'TripContext', 'MediaItem', 'ClipAnalysis'],
    moduleSpecifier: '../types'
});

constantsToMove.forEach(name => {
    const decl = appFile.getVariableStatement(s => s.getDeclarations().some(d => d.getName() === name));
    if (decl) {
        helpersFile.addVariableStatement({
            declarationKind: decl.getDeclarationKind(),
            declarations: decl.getDeclarations().map(d => ({
                name: d.getName(),
                type: d.getTypeNode()?.getText(),
                initializer: d.getInitializer()?.getText()
            })),
            isExported: true
        });
        decl.remove();
    }
});

functionsToMove.forEach(name => {
    const fn = appFile.getFunction(name);
    if (fn) {
        helpersFile.addFunction({
            name: fn.getName(),
            parameters: fn.getParameters().map(p => ({
                name: p.getName(),
                type: p.getTypeNode()?.getText(),
                initializer: p.getInitializer()?.getText()
            })),
            returnType: fn.getReturnTypeNode()?.getText(),
            statements: fn.getBodyText(),
            isExported: true
        });
        fn.remove();
    }
});

helpersFile.saveSync();
typesFile.saveSync();
appFile.saveSync();

console.log('Helpers and types extracted.');
