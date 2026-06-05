const { Project, SyntaxKind } = require('ts-morph');
const project = new Project({
    tsConfigFilePath: '/home/ubuntu/trendsync/mobile/tsconfig.json',
});

const outputScreenFile = project.getSourceFileOrThrow('src/screens/OutputScreen.tsx');

const stylesDecl = outputScreenFile.getVariableDeclarationOrThrow('styles');
const styleSheetCreateCall = stylesDecl.getInitializerIfKindOrThrow(SyntaxKind.CallExpression);
const stylesObject = styleSheetCreateCall.getArguments()[0].asKindOrThrow(SyntaxKind.ObjectLiteralExpression);

stylesObject.addPropertyAssignment({
    name: 'video',
    initializer: `{
    width: '100%',
    aspectRatio: 9 / 16,
    borderRadius: radii.md,
    backgroundColor: colors.camera,
    overflow: 'hidden',
  }`
});

outputScreenFile.saveSync();
console.log('styles.video added');
