const { Project, SyntaxKind } = require('ts-morph');
const fs = require('fs');
const path = require('path');

const project = new Project({
    tsConfigFilePath: '/home/ubuntu/trendsync/mobile/tsconfig.json',
});

const appFile = project.getSourceFileOrThrow('App.tsx');

const componentsToExtract = [
    'PrimaryButton', 'MetricPill', 'SectionHeader', 'Tag', 'PhaseRail', 'StatusStrip',
    'ClipIntelligence', 'ProducerBriefPanel', 'Field', 'LanguagePicker', 'ProviderPicker',
    'ProjectActionButton'
];

const screensToExtract = [
    'DashboardScreen', 'ContextScreen', 'PlanScreen', 'OutputScreen'
];

// Helper to get referenced styles
function getReferencedStyles(node) {
    const styles = new Set();
    node.forEachDescendant(descendant => {
        if (descendant.getKind() === SyntaxKind.PropertyAccessExpression) {
            const text = descendant.getText();
            if (text.startsWith('styles.')) {
                styles.add(text.replace('styles.', ''));
            }
        }
    });
    return Array.from(styles);
}

const stylesDecl = appFile.getVariableDeclarationOrThrow('styles');
const styleSheetCreateCall = stylesDecl.getInitializerIfKindOrThrow(SyntaxKind.CallExpression);
const stylesObject = styleSheetCreateCall.getArguments()[0].asKindOrThrow(SyntaxKind.ObjectLiteralExpression);
const allStyleProperties = stylesObject.getProperties();

const extractedStylesCache = new Map();

function extractFile(name, targetDir) {
    const fn = appFile.getFunction(name);
    if (!fn) {
        console.error(`Function ${name} not found`);
        return;
    }

    const refStyles = getReferencedStyles(fn);
    
    // Some components might use styles that are also used by others. 
    // We will duplicate the styles into the respective files.
    let stylesText = '';
    if (refStyles.length > 0) {
        stylesText = `\nconst styles = StyleSheet.create({\n`;
        for (const styleName of refStyles) {
            const prop = stylesObject.getProperty(styleName);
            if (prop) {
                stylesText += `  ${prop.getText()},\n`;
                extractedStylesCache.set(styleName, true);
            }
        }
        stylesText += `});\n`;
    }

    // Export the function by adding 'export ' before 'function'
    const fnText = fn.getText();
    const exportedFnText = fnText.startsWith('export') ? fnText : 'export ' + fnText;

    const blanketImports = `import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
`;

    const fileContent = `${blanketImports}\n\n${exportedFnText}\n${stylesText}`;

    const outPath = path.join('/home/ubuntu/trendsync/mobile/src', targetDir, `${name}.tsx`);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, fileContent);
    
    // Add import to App.tsx
    appFile.addImportDeclaration({
        moduleSpecifier: `./src/${targetDir}/${name}`,
        namedImports: [name],
    });

    // Remove function from App.tsx
    fn.remove();
}

componentsToExtract.forEach(name => extractFile(name, 'components'));
screensToExtract.forEach(name => extractFile(name, 'screens'));

// Remove extracted styles from App.tsx (only if they aren't used in App.tsx anymore)
const appStyles = getReferencedStyles(appFile);
allStyleProperties.forEach(prop => {
    const name = prop.getName();
    if (!appStyles.includes(name)) {
        prop.remove();
    }
});

appFile.saveSync();
console.log('Refactoring complete.');
