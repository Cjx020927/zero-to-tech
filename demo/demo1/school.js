const name = '清华大学'
const slogan = '天下没有难学的技术'

function getTel() {
    return '010-88888888'
}

function getCities() {
    return ['北京','上海','广州','深圳','成都']
}

// exports.name = name
// exports.slogan = slogan
// exports.getTel = getTel

module.exports = {name,slogan,getTel}