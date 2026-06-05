const { Project } = require('ts-morph');

const project = new Project({
    tsConfigFilePath: '/home/ubuntu/trendsync/mobile/tsconfig.json',
});

// Add all files
project.addSourceFilesAtPaths('/home/ubuntu/trendsync/mobile/src/components/**/*.tsx');
project.addSourceFilesAtPaths('/home/ubuntu/trendsync/mobile/src/screens/**/*.tsx');
project.addSourceFilesAtPaths('/home/ubuntu/trendsync/mobile/App.tsx');

const sourceFiles = project.getSourceFiles();

// To be safe, we will manually add some tricky imports like React hooks first
const reactHooks = ['useState', 'useEffect', 'useMemo', 'useCallback'];
const reactNativeImports = ['useWindowDimensions'];
const apiImports = ['mediaUrl'];
const helperImports = [
    'busyPhases', 'planningPhases', 'defaultRenderOptions', 'VIDEO_LENGTH_PRESETS',
    'projectFilters', 'projectSorts', 'LANGUAGES', 'LLM_PROVIDERS', 'providerModelPlaceholders',
    'tripContextFields', 'formatTimestamp', 'fallbackSegmentId', 'segmentForDecision', 'windowForDecision',
    'projectTitle', 'sessionTitle', 'phaseLabel', 'phaseFilter', 'phaseTone', 'formatUpdatedAt'
];

const componentFiles = [
    'PrimaryButton', 'MetricPill', 'SectionHeader', 'Tag', 'PhaseRail', 'StatusStrip',
    'ClipIntelligence', 'ProducerBriefPanel', 'Field', 'LanguagePicker', 'ProviderPicker',
    'ProjectActionButton'
];

sourceFiles.forEach(file => {
    // Basic react hooks
    const reactImport = file.getImportDeclaration(d => d.getModuleSpecifierValue() === 'react');
    if (reactImport) {
        reactHooks.forEach(hook => {
            if (file.getText().includes(hook) && !reactImport.getNamedImports().some(n => n.getName() === hook)) {
                reactImport.addNamedImport(hook);
            }
        });
    }

    const rnImport = file.getImportDeclaration(d => d.getModuleSpecifierValue() === 'react-native');
    if (rnImport) {
        reactNativeImports.forEach(i => {
            if (file.getText().includes(i) && !rnImport.getNamedImports().some(n => n.getName() === i)) {
                rnImport.addNamedImport(i);
            }
        });
    }

    // Types
    const typesImport = file.getImportDeclaration(d => d.getModuleSpecifierValue() === '../types') ||
                        file.getImportDeclaration(d => d.getModuleSpecifierValue() === './src/types');
    if (typesImport) {
        const missingTypes = ['ProjectFilter', 'ProjectSort', 'ProjectAction'];
        missingTypes.forEach(t => {
            if (file.getText().includes(t) && !typesImport.getNamedImports().some(n => n.getName() === t)) {
                typesImport.addNamedImport(t);
            }
        });
    }

    // Determine path to helpers, api, components based on file location
    const filePath = file.getFilePath();
    const isAppTsx = filePath.endsWith('App.tsx');
    const isComponent = filePath.includes('/src/components/');
    const isScreen = filePath.includes('/src/screens/');

    const helpersPath = isAppTsx ? './src/utils/helpers' : '../utils/helpers';
    const apiPath = isAppTsx ? './src/api' : '../api';
    const componentsPrefix = isAppTsx ? './src/components/' : isComponent ? './' : '../components/';

    // API
    const apiImportDecl = file.getImportDeclaration(d => d.getModuleSpecifierValue() === apiPath);
    if (apiImportDecl) {
        apiImports.forEach(i => {
            if (file.getText().includes(i) && !apiImportDecl.getNamedImports().some(n => n.getName() === i)) {
                apiImportDecl.addNamedImport(i);
            }
        });
    }

    // Helpers
    const helpersUsed = helperImports.filter(h => file.getText().includes(h) && !file.getVariableStatement(s => s.getDeclarations().some(d => d.getName() === h)) && !file.getFunction(h));
    if (helpersUsed.length > 0) {
        let hImport = file.getImportDeclaration(d => d.getModuleSpecifierValue() === helpersPath);
        if (!hImport) {
            hImport = file.addImportDeclaration({ moduleSpecifier: helpersPath });
        }
        helpersUsed.forEach(h => {
            if (!hImport.getNamedImports().some(n => n.getName() === h)) {
                hImport.addNamedImport(h);
            }
        });
    }

    // Components
    const compsUsed = componentFiles.filter(c => file.getText().includes(`<${c}`) || file.getText().includes(` ${c}(`));
    compsUsed.forEach(c => {
        if (file.getBaseNameWithoutExtension() === c) return; // don't import self
        
        let specifier = componentsPrefix + c;
        let cImport = file.getImportDeclaration(d => d.getModuleSpecifierValue() === specifier);
        if (!cImport) {
            file.addImportDeclaration({
                moduleSpecifier: specifier,
                namedImports: [c]
            });
        }
    });

    file.fixMissingImports();
});

project.saveSync();
console.log('Imports fixed.');
