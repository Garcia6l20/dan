export interface Target {
    name: string;
    fullname: string;
    output: string;
    buildPath: string;
    executable: boolean;
    type: string;
};

export function isTarget(object: any): object is Target {
    return object instanceof Object
        && 'name' in object
        && 'fullname' in object
        && 'output' in object
        && 'buildPath' in object
        && 'executable' in object
        && 'type' in object;
}
